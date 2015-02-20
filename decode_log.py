#!/usr/bin/env python
import sys
import zlib
import struct
import array
from cStringIO import StringIO

def decode_varint(inf):
    value = 0
    base = 1
    l = 0
    while True:
        raw_byte = inf.read(1)
        if len(raw_byte) == 0:
            return 0, 0
        raw_byte = raw_byte[0]
        l += 1
        val_byte = ord(raw_byte)
        value += (val_byte & 0x7f) * base
        if (val_byte & 0x80):
            base *= 128
        else:
            return (value, l)

def decode_string(inf):
    strlen, _ = decode_varint(inf)
    return inf.read(strlen)

def decode_double(inf):
    return struct.unpack('!d', inf.read(8))[0]

def decode_int(inf):
    return struct.unpack('!i', inf.read(4))[0]

def decode_float(inf):
    return struct.unpack('!f', inf.read(4))[0]

def decode_short(inf):
    return struct.unpack('!h', inf.read(2))[0]

def decode_ushort(inf):
    return struct.unpack('!H', inf.read(2))[0]

def decode_byte(inf):
    return struct.unpack('b', inf.read(1))[0]

def decode_bool(inf):
    return struct.unpack('b', inf.read(1))[0] != 0

def decode_position(inf):
    p = struct.unpack('!Q', inf.read(8))[0]
    return ((val >> 38), ((val >> 26) & 0xFFF), (val << 38 >> 38))

class GameState(object):
    player_eid = None
    pos = None

    def __init__(self):
        self.pos = [0.0, 0.0, 0.0]
        self.chunks = {}
        self.diamonds = []

class Chunk(object):
    def __init__(self):
        self.x = 0
        self.y = 0
        self.blocks = array.array('H', (0 for _ in xrange(65536)))

def decode_join_game(data, state):
    state.player_eid, gm, dim, diff, maxplayers = struct.unpack('iBbBB', data.read(8))
    print 'EID:', state.player_eid
    print 'Gamemode:', gm
    print 'Dimension:', dim
    print 'Difficulty:', diff
    print 'Max players:', maxplayers

def test_flag(flags, flag):
    return 0 != (flags & flag)

def decode_player_position(data, state):
    pos = (decode_double(data), decode_double(data), decode_double(data))
    decode_float(data)
    decode_float(data)
    flags = decode_byte(data)
    rel = (test_flag(flags, 0x01), test_flag(flags, 0x02), test_flag(flags, 0x03))
    for i in range(3):
        if rel[i]:
            state.pos[i] += pos[i]
        else:
            state.pos[i] = pos[i]
    print 'New player position: %s' % (', '.join([str(p) for p in state.pos]))

def read_chunk(data, state, cx, cz, bitmask, has_light):
    chunk_key = (cx, cz)
    if chunk_key in state.chunks:
        chunk = state.chunks[chunk_key]
    else:
        chunk = Chunk()
        state.chunks[chunk_key] = chunk
    for cy in range(16):
        y = cy * 16
        if not test_flag(bitmask, 1<<cy):
            continue
        blocks_size = 2*16*16*16
        chunk_ofs = y*16*16
        blocks = data.read(blocks_size)
        k = 0
        while k < blocks_size:
            blockval = ord(blocks[k]) + (ord(blocks[k+1]) << 8)
            blockid = blockval >> 4
            dx = chunk_ofs % 16
            dz = (chunk_ofs / 16) % 16
            dy = chunk_ofs / 256
            if blockid == 56:
                print 'Diamond ore at %d, %d, %d' % (dx + cx*16, dy, dz + cz*16)
                state.diamonds.append((dx + cx*16, dy, dz + cz*16))
            k += 2
            chunk.blocks[chunk_ofs] = blockval
            chunk_ofs += 1
        blocklights = data.read(8*16*16)
        if has_light:
            skylights = data.read(8*16*16)
    biomes = data.read(16*16)
    if (len(biomes) != 16*16):
        print 'Premature end of chunk collection'

def decode_and_save_chunk(data, stats):
    cx = decode_int(data)
    cz = decode_int(data)
    cont = decode_bool(data)
    bitmask = decode_ushort(data)
    datasize = decode_varint(data)
    read_chunk(data, stats, cx, cz, bitmask, True)

def decode_and_save_chunks(data, stats):
    has_light = decode_bool(data)
    col_count, _ = decode_varint(data)
    chunk_meta = []
    for i in range(col_count):
        chunk_meta.append((decode_int(data), decode_int(data), decode_ushort(data)))
        #print 'Chunk at %d, %d' % (chunk_meta[-1][0], chunk_meta[-1][1])
    for cx, cz, bitmask in chunk_meta:
        read_chunk(data, stats, cx, cz, bitmask, has_light)


state = GameState()
inf = sys.stdin
compr = -1
while True:
    plen, _ = decode_varint(inf)
    #print 'Packet length: %d' % plen
    if plen == 0:
        break
    data = inf.read(plen)
    if len(data) != plen:
        print 'Premature end of packet'
        break
    data = StringIO(data)
    if compr >= 0:
        zlen, _ = decode_varint(data)
        if zlen:
            unzdata = zlib.decompress(data.read())
            if len(unzdata) != zlen:
                print 'Failed to decompress packet (actual %d bytes, expected %d bytes)' % (len(unzdata), zlen)
            data = StringIO(unzdata)
    pid, _ = decode_varint(data)
    if pid == 0x03:
        compr, _ = decode_varint(data)
        print 'New compression threshold:', compr
    elif pid == 0x00:
        pass
    elif pid == 0x01:
        decode_join_game(data, state)
    elif pid == 0x05:
        print 'Spawn point'
    elif pid == 0x08:
        decode_player_position(data, state)
    elif pid == 0x09:
        print 'Selected inventory slot %d' % decode_byte(data)
    elif pid == 0x21:
        print 'Map chunk'
        decode_and_save_chunk(data, state)
    elif pid == 0x26:
        print 'Map chunks'
        decode_and_save_chunks(data, state)
    elif pid == 0x2F:
        print 'Inventory window slot'
    elif pid == 0x30:
        print 'Inventory window contents'
    elif pid == 0x37:
        print 'Player stats'
    elif pid == 0x38:
        print 'Player list update'
    elif pid == 0x39:
        print 'Player abilities'
    elif pid == 0x3F:
        print 'Plugin channel data for channel %s' % decode_string(data)
    elif pid == 0x41:
        print 'Server difficulty'
    elif pid == 0x44:
        print 'World border'
    else:
        print 'Packet ID: 0x%02X' % pid

plr = (-46, 11, -86)
def dist(d):
    x, y, z = d
    dx = x - plr[0]
    dy = 0
    dz = z - plr[2]
    return dx*dx + dy*dy + dz*dz


state.diamonds.sort(key=lambda d:dist(d))
for x, y, z in state.diamonds:
    print '%d\t%d\t%d' % (x, y, z)
    

