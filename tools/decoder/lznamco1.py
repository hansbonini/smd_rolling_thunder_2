#!/usr/bin/python
import io
import os
import sys

FROM_START = 0
FROM_CURRENT = 1
FROM_END = 2


class Input:
  def __init__(self, filename, offset):
    """ Initialize a input file and put the cursor on specified offset """
    self.__input__ = open(filename, 'rb')
    self.__input__.seek(offset, FROM_START)

  def read(self, bytes):
    """ Read N bytes from input file, return as int """
    return int.from_bytes(self.__input__.read(bytes), byteorder='big')

  def close(self):
    """ Close input file """
    self.__input__.close()


class Output:
  def __init__(self, filename):
    """ Open output file and set specified offset as filename """
    self.__output__ = open(format(filename, '08X') + '.gen', 'wb')

  def write(self, value):
    """ Write a byte value to output file """
    self.__output__.write(value)

  def close(self):
    """ Close output file """
    self.__output__.close()


class LZDecoder:
  def __init__(self, maxlen):
    """ Prepare decoder """
    self.__maxlen__ = maxlen
    self.__lzwindow__ = io.BytesIO()
    self.__lzwindowmax__ = 0xFFF
    self.__lzwindowcounter__ = 0xFEE
    self.__bitmask__ = 0x0

  def running(self):
    """ Return decoder status; if True status is running """
    return self.__maxlen__ > 0

  def is_extended(self, value):
    """ Check if a value is extended (word) """
    if ((int(value) & 0xFF00) > 0):
      return True
    return False

  def get_bitmask(self):
    """ Returns current bitmask value"""
    return self.__bitmask__

  def set_bitmask(self, value):
    """ Set a new bitmask value """
    self.__bitmask__ = value | 0xFF00

  def shiftr_bitmask(self):
    """ Shifts Right current bitmask value """
    self.__bitmask__ = self.__bitmask__ >> 1

  def test_bitmask(self, bit):
    """ Test an specified bit of current bitmask value """
    if (int((format(self.__bitmask__, '016b')[2:])[bit]) == 0):
      return True
    return False

  def get_compressed(self, value):
    """ Decompress LZ Pair and returns values as List """
    output = []
    lz_data = (value >> 8) & 0xFF
    lz_counter = value & 0xFF
    # Define the relative offset on LZ Window
    lz_offset = ((lz_counter & 0xF0) << 4) | lz_data
    # Define the LZ Counter for repeat data N times
    lz_counter = (lz_counter & 0xF) + 0x2
    # Start Repeat Loop
    while (lz_counter >= 0):
      # Seek the window on LZ Offset and get the LZ Data
      self.__lzwindow__.seek(lz_offset, FROM_START)
      lz_data = (lz_data & 0xFF00) + \
          int.from_bytes(self.__lzwindow__.read(1), byteorder='big')
      # Write the LZ data to the output
      output.append((lz_data & 0xFF).to_bytes(1, byteorder='big'))
      # Seek the LZ Window on current LZ Window Counter value and write the current LZ Data (LZBuffer)
      self.__lzwindow__.seek(self.__lzwindowcounter__, FROM_START)
      self.__lzwindow__.write((lz_data & 0xFF).to_bytes(1, byteorder='big'))
      # Increment LZ Window Counter
      self.__lzwindowcounter__ = (
          self.__lzwindowcounter__ + 0x1) & self.__lzwindowmax__
      # Increment LZ Offset
      lz_offset = (lz_offset + 0x1) & self.__lzwindowmax__
      # Decrement number of data to decompress
      self.__maxlen__ -= 0x1
      # Decrement LZ Loop counter
      lz_counter -= 0x1
    return output

  def get_uncompressed(self, value):
    """ Return Uncompressed Data after add this to Decomp Buffer """
    # Seek the LZ Window on current LZ Window Counter value and write the current LZ Data (LZBuffer)
    self.__lzwindow__.seek(self.__lzwindowcounter__, FROM_START)
    self.__lzwindow__.write((value & 0xFF).to_bytes(1, byteorder='big'))
    # Increment LZ Window Counter
    self.__lzwindowcounter__ = (
        self.__lzwindowcounter__ + 0x1) & self.__lzwindowmax__
    # Decrement number of data do decompress
    self.__maxlen__ -= 0x1
    # Return Data to Output
    return (value & 0xFF).to_bytes(1, byteorder='big')


if __name__ == '__main__':
  offset = int(sys.argv[1], 16)
  rom = Input('rolling2.gen', offset)
  output = Output(offset)

  # Prepare for decompression
  decoder = LZDecoder(rom.read(2))
  while decoder.running():
    decoder.shiftr_bitmask()
    # If bit #8 == 0 get a new Bitmask
    if(decoder.test_bitmask(-9)):
      decoder.set_bitmask(rom.read(1))
    # If bit #0 == 0 and bitmask is Extended decompress a pair
    if(decoder.test_bitmask(-1) and decoder.is_extended(decoder.get_bitmask())):
      for decompressed_byte in decoder.get_compressed(rom.read(2)):
        output.write(decompressed_byte)
    else:
      output.write(decoder.get_uncompressed(rom.read(1)))
  output.close()
  rom.close()
