# Most of the underlying data about how CT encodes strings is due to
# https://bisqwit.iki.fi/jutut/ctcset.html

from __future__ import annotations

import pickle

import byteops


class Node:

    def __init__(self):
        self.held_substring = None
        self.held_substring_index = None
        self.children = dict()

    def print_tree(self):

        for key in self.children.keys():
            print(f"following {key:02X}")
            self.children[key].print_tree()

        if len(self.children.keys()) == 0:
            print(f"leaf: index = {self.held_substring_index} "
                  f"subsring = {self.held_substring}")


# Note: This is not really a Huffman tree.  It's just an organizational tree
# structure for holding the compression substrings.
class CTHuffmanTree:

    def __init__(self, substrings: list[bytearray]):
        self.root = Node()

        self.substrings = substrings

        for index, substring in enumerate(substrings):
            self.add_substring(substring, index)

    def add_substring(self, substring: bytearray, index: int):
        self.__add_substring_r(self.root, substring, index, 0)

    def __add_substring_r(self,
                          node: Node,
                          substring: bytearray,
                          substring_index: int,
                          cur_pos: int = 0):

        if cur_pos == len(substring):
            node.held_substring = substring
            node.held_substring_index = substring_index
        else:
            cur_byte = substring[cur_pos]
            if cur_byte in node.children.keys():
                self.__add_substring_r(node.children[cur_byte],
                                       substring,
                                       substring_index, cur_pos+1)
            else:
                node.children[cur_byte] = Node()
                self.__add_substring_r(node.children[cur_byte],
                                       substring,
                                       substring_index, cur_pos+1)

    def compress(self, string: bytearray):

        ret_string = bytearray()

        pos = 0
        while pos < len(string):
            (ind, length) = self.match(string, pos)
            # print(ind, length)
            if ind is not None:
                if ind in range(0, 0x7F):
                    # substr = string[pos:pos+length]
                    # print('matched ' + CTString.ct_bytes_to_ascii(substr))
                    # string[pos:pos+length] = [ind + 0x21]
                    ret_string.append(ind+0x21)
                # Index 0x7F is '...', but this is not actually used.
                # Instead, '...' is represented by 0xF1
                elif ind == 0x7F:
                    ret_string.append(0xF1)
                pos += length
            else:
                ret_string.append(string[pos])
                pos += 1

        return ret_string

    def match(self, string: bytearray, pos: int):

        return self.match_r(string, pos, self.root)

    # Traverse the tree character by character.  Find the first node with a
    # non-None substring on the way back.
    def match_r(self, string: bytearray, pos: int, node: Node):

        if pos == len(string):
            return node.held_substring_index, 0

        if string[pos] in node.children.keys():
            # print(f"searching child {string[pos]:02X}")
            (substr, match_len) = self.match_r(string,
                                               pos+1,
                                               node.children[string[pos]])

            if substr is not None:
                return substr, match_len + 1
            else:
                return node.held_substring_index, 0
        else:
            return node.held_substring_index, 0


# CTString extends bytearray because it is just a bytearray with a few extra
# methods for converting to python string and compression.
class CTString(bytearray):

    # This list might not be exactly right.  I need to encounter each keyword
    # in a flux file before I know exactly what name flux uses.

    # weirdness:
    # Bisqwit says 0x05 is line break and 0x06 is line break +3 spaces.
    # It looks like 0x06 is just the normal line break in scripts.
    # So I've made 0x06 match with TF's {linebreak}.
    # Bisquit's 'Pause and dialog emptying' is TF's {page break}
    keywords = [
        'null', 'unused 0x01', 'unused 0x02', 'delay',
        'unused 0x04', 'linebreak+0', 'line break',
        'pause linebreak', 'pause linebreak+3',
        'instant full break', 'page break+3',
        'full break', 'page break',
        'value 8', 'value 16', 'value 32',
        'unused 0x10', 'prev substr', 'tech name',
        'crono', 'marle', 'lucca', 'robo', 'frog', 'ayla',
        'magus', 'crononick', 'pc1', 'pc2', 'pc3', 'nadia',
        'item', 'epoch'
    ]

    symbols = [
        '!', '?', '/', '\"1', '\"2', ':', '&', '(', ')', '\'', '.',
        ',', '=', '-', '+', '%', 'note', ' ', '{:heart:}', '...',
        '{:inf:}', 'none'
    ]

    huffman_table = pickle.load(open('./pickles/huffman_table.pickle', 'rb'))
    huffman_tree = CTHuffmanTree(huffman_table)

    # There's nothing special that we do for CTStrings.
    # New behavior, no new data.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def from_str(cls, string: str, compress: bool = False):
        ct_str = cls()

        pos = 0

        while pos < len(string):
            (ct_bytes, pos) = cls.get_token(string, pos)
            ct_str.extend(ct_bytes)

        if compress:
            ct_str = cls.huffman_tree.compress(ct_str)

        return ct_str

    @classmethod
    def get_token(cls, string: str, pos: int) -> (bytes, int):
        '''
        Gets the next byte of data for a ct string.  Returns that byte and the
        position of where the byte after begins.
        '''

        char = string[pos]
        ct_bytes = None
        # print(char, pos)
        if char.isupper():
            # Upper case chars are in range(0xA0, 0xBA)
            ct_char = (ord(char) - 0x41) + 0xA0
            length = 1
        elif char.islower():
            # Lower case chars are in range(0xBA, 0xD4)
            ct_char = (ord(char) - 0x61) + 0xBA
            length = 1
        elif char.isnumeric():
            # Digits are in range(0xD4, 0xDE)
            ct_char = (ord(char) - 0x30) + 0xD4
            length = 1
        elif char in CTString.symbols:
            # Symbols (see CTString.symbols) are in range(0xDE, 0xE
            ct_char = CTString.symbols.index(char) + 0xDE
            length = 1
        elif char == '\"':
            quote_str = string[pos:pos+2]
            ct_char = CTString.symbols.index(quote_str) + 0xDE
            length = 2
        elif char == '{':
            # '{' marks the start of a keyword like Crono's name or an item.
            # CTString.keywords has all of these listed.

            # grab the keyword itself
            keyword = string[pos+1:].split('}')[0].lower()
            length = len(keyword) + 2  # keyword + {}

            if keyword in CTString.keywords:
                # keywords are in range(0, 21) so there's no shift
                ct_char = CTString.keywords.index(keyword)
                end = pos + length

                # Sometimes TF uses \r\n to stand for a CT linebreak.
                # Sometimes it throws it in there as formatting after a
                # '{linebreak}' in the ascii.  We need to strip out the
                # latter \r\n instances.

                # '\r\n' after a break char is a fake break
                break_chars = (5, 6, 7, 8, 10, 11, 12)

                if ct_char in break_chars and \
                   end+2 < len(string) and \
                   string[end:end+2] == '\r\n':
                    length += 2
            elif keyword in CTString.symbols:
                # quotation marks are in there too as {"1} and {"2}
                ct_char = CTString.symbols.index(keyword) + 0xDE
            elif keyword.split(' ')[0] == 'delay':
                vals = [0x03, int(keyword.split(' ')[1], 16)]
                ct_bytes = bytes(vals)
            else:
                print(keyword.split(' ')[0])
                print(f"unknown keyword \'{keyword}\'")
                exit()
        elif char == '\r' and pos+1 < len(string) and string[pos+1] == '\n':
            length = 2
            ct_char = 5
        else:
            print(f"unknown symbol \'{char}\'")
            exit()

        # print(f"char={char}, pos={pos}, ctchar={ct_char:02X}")
        # returning new position instead of length so that we can do things
        # like (char, pos) = get_token(str, pos) to update in a loop.
        if ct_bytes is None:
            ct_bytes = bytes([ct_char])

        return (ct_bytes, pos+length)

    @classmethod
    def from_ascii(cls, string: str):
        '''Turns an ascii string (+{keywords}) into a CTString.'''
        ret_str = CTString()

        pos = 0
        while pos < len(string): 
            (ct_bytes, pos) = cls.get_token(string, pos)
            ret_str.extend(ct_bytes)

        return ret_str

    def get_compressed(self):
        return CTString(CTString.huffman_tree.compress(self))

    def compress(self):
        self[:] = CTString(self.huffman_tree.compress(self))

    @classmethod
    def compress_bytearray(cls, array: bytearray):
        return cls(cls.huffman_tree.compress(array))

    @classmethod
    def ct_bytes_to_techname(cls, array: bytes):
        return CTString(array).to_ascii(techname=True)

    @classmethod
    def ct_bytes_to_ascii(cls, array: bytes):
        return CTString(array).to_ascii()

    def to_ascii(self, techname=False):
        '''Turns this CTString into a python string'''

        ret_str = ''

        pos = 0
        while pos < len(self):
            cur_byte = self[pos]

            if cur_byte in range(0, 0x21):
                # special symbols
                keyword = self.keywords[cur_byte]
                if keyword == 'delay':
                    pos += 1
                    keyword += ' ' + str(self[pos])
                ret_str += f"{{{keyword}}}"
            elif cur_byte in range(0x21, 0xA0):
                if techname and cur_byte == 0x2F:
                    ret_str += '*'
                else:
                    x = self.huffman_table[cur_byte-0x21]
                    # print(f"substr: {x}")
                    x = CTString(x).to_ascii()
                    # print(f"substr: {x}")
                    ret_str += x
                    # ret_str += f"{{:subst {cur_byte:02X}:}}"
            elif cur_byte in range(0xA0, 0xBA):
                ret_str += chr(cur_byte-0xA0+0x41)
            elif cur_byte in range(0xBA, 0xD4):
                ret_str += chr(cur_byte-0xBA+0x61)
            elif cur_byte in range(0xD4, 0xDE):
                ret_str += f"{cur_byte-0xD4}"
            elif cur_byte in range(0xDE, 0xF4):
                symbol = self.symbols[cur_byte-0xDE]
                if symbol in ('note', '\"1', '\"2'):
                    symbol = '{' + symbol + '}'
                ret_str += symbol
            elif cur_byte == 0xFF:
                # enemies edited in TF seem to get FFs in their names
                ret_str += ' '
            else:
                ret_str += '[:bad:]'
                print(f"Bad byte: {cur_byte:02X}")
                exit()

            pos += 1

        return ret_str


class CTNameString(bytearray):
    name_symbols = {
        0x00: '{none00}',
        0x20: '{sword}',
        0x21: '{bow}',
        0x22: '{gun}',
        0x23: '{arm}',
        0x24: '{blade}',
        0x25: '{fist}',
        0x26: '{scythe}',
        0x27: '{helm}',
        0x28: '{armor}',
        0x29: '{acc}',
        0x2A: '{h}',
        0x2B: '{m}',
        0x2C: '{p}',
        0x2D: ':',
        0x2E: '{shield}',
        0x2F: '*',
        0x30: '#',
        0x31: '{->}',
        0x32: '{boxtl}',
        0x33: '{boxbr}',
        0x34: '+',
        # There are more, but weird capital versions that dont come up.
        0xDE: '!', 0xDF: '?', 0xE0: '/', 0xE1: '\"1', 0xE2: '\"2', 0xE3: ':',
        0xE4: '&', 0xE5: '(', 0xE6: ')', 0xE7: '\'', 0xE8: '.',
        0xE9: ',', 0xEA: '=', 0xEB: '-', 0xEC: '+', 0xED: '%',
        0xEE: '{noneEE}', 0xEF: '{endpadEF}', 0xF0: '{:heart:}',
        0xFF: ' '
    }

    _lowercase_dict = {ord(x)-0x61+0xBA: x
                       for x in 'abcdefghijklmnopqrstuvwxyz'}
    _uppercase_dict = {ord(x)-0x41+0xA0: x
                       for x in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'}
    _number_dict = {ord(x)-0x30+0xD4: x
                    for x in '0123456789'}
    byte_to_symbol_dict = {**name_symbols, **_lowercase_dict,
                           **_uppercase_dict,
                           **_number_dict}
    symbol_to_byte_dict = {value: key
                           for (key, value) in byte_to_symbol_dict.items()}

    @classmethod
    def from_string(cls, string: str, length: int = 0xB, pad_val: int = 0xEF):
        str_pos = 0

        ct_bytes = bytearray()
        while str_pos < len(string):
            found = False
            for (key, value) in cls.symbol_to_byte_dict.items():
                if string[str_pos:].startswith(key):
                    ct_bytes.append(value)
                    str_pos += len(key)
                    found = True
                    break

            if not found:
                raise ValueError(string[str_pos:])

        if len(ct_bytes) > length:
            ct_bytes = ct_bytes[0:length+1]
        elif len(ct_bytes) < length:
            ct_bytes.extend([pad_val for x in range(length-len(ct_bytes))])

        pos = len(ct_bytes) - 1
        while pos >= 0 and ct_bytes[pos] == 0xFF:
            ct_bytes[pos] = pad_val
            pos -= 1

        return CTNameString(ct_bytes)

    def __str__(self):
        try:
            ind = self.index(0xEF)
        except ValueError:
            ind = len(self)
        string = ''.join(self.byte_to_symbol_dict[x] for x in self[0:ind])
        return string


# This table is never changed by TF, so we should only have to read it once
# and pickle it.
def get_huffman_table(rom: bytearray) -> list[bytearray]:
    '''Pulls the substring table from the rom.'''
    ptr_table_addr = 0x1EFA00
    bank = (ptr_table_addr & 0xFF0000)

    huffman_table = []

    for i in range(128):
        ptr = ptr_table_addr + 2*i
        start = byteops.get_value_from_bytes(rom[ptr:ptr+2]) + bank

        substr_len = rom[start]
        substr_start = start+1
        substr_end = substr_start+substr_len

        huffman_table.append(rom[substr_start:substr_end])

    return huffman_table


def main():
    pass


if __name__ == '__main__':
    main()
