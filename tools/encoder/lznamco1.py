#!/usr/bin/python
import sys, os, io
import copy

FROM_START = 0
FROM_CURRENT = 1
FROM_END = 2

class Input:
    def __init__(self, filename):
        """ Initialize a input file and put the cursor on specified offset """
        self.__input__ = open(format(filename, '08X')+'.gen','rb')
        self.__input__.seek(0, FROM_END);
        self.__sizeof__ = self.__input__.tell()
        self.__input__.seek(0, FROM_START);

    def read(self, bytes):
        """ Read N bytes from input file, return as int """
        return int.from_bytes(self.__input__.read(bytes), byteorder='big')

    def seek(self, offset):
        self.__input__.seek(offset, FROM_START);

    def sizeof(self):
        return self.__sizeof__

    def close(self):
        """ Close input file """
        self.__input__.close()

    def get_offset(self):
        return self.__input__.tell()

class Output:
    def __init__(self, filename):
        """ Open output file and set specified offset as filename """
        self.__output__ = open(format(filename, '08X')+'_compressed.gen', 'wb')

    def write(self, value):
        """ Write a byte value to output file """
        self.__output__.write(value)

    def sizeof(self):
        return self.__output__.tell()

    def close(self):
        """ Close output file """
        self.__output__.close()

class LZWindow:
    def __init__(self):
        self.__max__ = 0xFFF
        self.__current__ = 0xFEE
        self.__window__ = []
        for x in range(0, self.__max__+1):
            self.__window__.append(0x0)

    def max(self):
        return self.__max__

    def get_current(self):
        return self.__current__

    def append(self, value):
        self.__window__[self.__current__] = value
        self.__current__ += 1
        self.__current__ = self.__current__&self.__max__

    def window(self):
        return self.__window__

    def get(self, key):
        return self.__window__[key]

class LZOptimizer:
    def __init__(self, _input, lzwindow, match):
        """ Initialize the LZ data optimizer """
        self._input = _input
        self.lzwindow = lzwindow
        self.match = match
        self.current_input_offset = self._input.get_offset()
        self.current_lzwindow_offset = self.lzwindow.get_current()
        self.possible_chains = (self.lzwindow.window()).count(self.match)
        self.probed_chains = 0
        self.matches = []

    def run(self):
        """ Probe possible chains and choose the best match """
        while self.probed_chains < self.possible_chains:
            index = 0
            self._input.seek(self.current_input_offset)
            current = self.current_lzwindow_offset&self.lzwindow.max()
            end = (self.current_lzwindow_offset-self.lzwindow.max()-0x1)
            while current >= end:
                if (self.lzwindow.get(current&self.lzwindow.max()) == self.match):
                    length = self.probe_match_length(current)
                    if (length > 0x2) and (index < 0):
                        self.matches.append((index, length-0x1))
                    self.probed_chains += 1
                    if not (self.probed_chains < self.possible_chains):
                        break
                current-=1
                index-=1
        if len(self.matches) > 0:
            return self.best_match()
        return (0,0)

    def probe_match_length(self, current):
        """ Probe matched chain length """
        self._input.seek(self.current_input_offset)
        temp_window = copy.copy(self.lzwindow)
        temp_window.append(temp_window.get((current)&self.lzwindow.max()))
        next_match = self._input.read(1)
        length = 1
        while next_match == temp_window.get((current+length)&self.lzwindow.max()):
            if length > 0x11:
                break
            temp_window.append(temp_window.get((current+length)&self.lzwindow.max()))
            next_match = self._input.read(1)
            length += 1
        return length

    def best_match(self):
        """ Choose best match in possible matches """
        lst = []
        lst_by_index = sorted(self.matches, key=lambda x: x[0], reverse=True)
        lst_by_length = sorted(self.matches, key=lambda x: x[1])
        for match in enumerate(lst_by_length):
            lst.append((match[0]+lst_by_length.index(match[1]), match[0]))
        return self.matches[sorted(lst, key=lambda x: x[0])[0][1]]

class LZEncoder:
    def __init__(self, _input, _output):
        """ Start LZ Encoder """
        self._input = _input
        self._output = _output
        self._chain = (0,0)
        self._buffer = []
        self._bitmask = []
        self._cycle = 0
        self.maxlen = self._input.sizeof()
        self.curlen = self.maxlen
        self.lzwindow = LZWindow()
        self.print_starting()
        # Write length of decompressed data
        _output.write(((self.maxlen >> 8)&0xFF).to_bytes(1, byteorder='big'))
        _output.write((self.maxlen&0xFF).to_bytes(1, byteorder='big'))

    def run(self):
        """ Run LZ Encoder """
        while self.curlen > 0:
            # Display task percentage completed
            self.print_progress()
            # Write Bitmask and Data to output
            if (len(self._bitmask) == 8):
                self._cycle += 1
                self.write_bitmask_to_output()
                self.write_buffer_to_output()
            # Check for possible chains and choose the best match
            current_input_offset = self._input.get_offset()
            current_match = self._input.read(1)
            if self.has_output_data():
                possible_chains = (self.lzwindow.window()).count(current_match)
                # If possible chains in buffer run Optimizer to get best chain
                if possible_chains > 0:
                    optimizer = LZOptimizer(self._input, self.lzwindow, current_match)
                    self._chain = optimizer.run()
            # If has a LZ Chain process LZ Pair
            if self.has_chain():
                self._input.seek(current_input_offset+self._chain[1]+0x1)
                length = self._chain[1]
                offset = (self.lzwindow.get_current()-abs(self._chain[0]))&self.lzwindow.max()
                pair = (offset&0xFF)<<8 | ((offset>>4)&0xF0 | ((length-0x2)&0xF))
                # Append Pair to Buffer
                self._buffer.append(((pair>>8)&0xFF).to_bytes(1, byteorder='big'))
                self._buffer.append((pair&0xFF).to_bytes(1, byteorder='big'))
                # Append Chain to Window
                for count in range(0, length+1):
                    self.lzwindow.append(self.lzwindow.get((offset+count)&self.lzwindow.max()))
                    self.curlen -= 1
                self._chain = (0,0)
                # Set Bitmask 0 => encoded chain
                self._bitmask.append(0)
            else:
                # If not a encoded chain append readed byte to Buffer and Window
                self._input.seek(current_input_offset)
                byte_read = self._input.read(1)
                self.lzwindow.append(byte_read)
                self._buffer.append(byte_read.to_bytes(1, byteorder='big'))
                # Set Bitmask 1 => decoded byte
                self._bitmask.append(1)
                self.curlen-=1

    def print_starting(self):
        """ Print encoder start message """
        print('[*] Starting data encoding with LZ...')

    def print_progress(self):
        """ Print encoder progress """
        print('{0:.2f}%'.format(100-(self.curlen*100/self.maxlen)))

    def print_ratio(self):
        """ Print encoder ratio """
        input_size = ((self._input.sizeof()*100)/self._input.sizeof())
        output_size = ((self._output.sizeof()*100)/self._input.sizeof())
        print('[+] Success encoded with a ratio '+str(round(input_size/output_size))+':1')

    def has_chain(self):
        """ Check if has a valid chain to compress """
        return self._chain[1] >= 2

    def has_output_data(self):
        """ Check if has data in output file """
        return self._cycle >= 1

    def write_bitmask_to_output(self):
        """ Write LZ bitmask control byte to output """
        self._bitmask.reverse()
        self._output.write(int('0b'+''.join(map(str, self._bitmask)),2).to_bytes(1, byteorder='big'))
        self._bitmask = []

    def write_buffer_to_output(self):
        """ Write encoded buffer to output """
        for value in self._buffer:
            self._output.write(value)
        self._buffer = []


if __name__=='__main__':
    offset = int(sys.argv[1],16)
    encoder = LZEncoder(Input(offset), Output(offset))
    encoder.run()
    encoder.print_ratio()
