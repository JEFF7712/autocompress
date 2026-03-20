// compress.cpp — CANDIDATE FILE (agent edits this)
//
// Implement a compressor/decompressor for the Hutter Prize autoresearch loop.
// Score = total compressed bytes across all benchmark files. Lower is better.
//
// Usage (built and run by train.py):
//   ./compress c <input> <output>   — compress
//   ./compress d <input> <output>   — decompress
//
// ============================================================
// CANDIDATE SECTION — tune and experiment with these
// ============================================================
//
// Current approach: LZMA2 with tunable parameters.
// Ideas to try: increase DICT_SIZE, tune LC/LP/PB, add BCJ/delta
// preprocessing, try higher-order context models, PPM, etc.

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <lzma.h>

static const uint32_t LEVEL     = 9;          // 0-9 (compression level)
static const uint64_t DICT_SIZE = 1u << 26;   // 64 MB dictionary (2^n or 3*2^n)
static const uint32_t LC        = 4;           // literal context bits (0-4, lc+lp <= 4)
static const uint32_t LP        = 0;           // literal position bits (0-4)
static const uint32_t PB        = 0;           // position bits (0-4)
static const bool     EXTREME   = true;        // extra compression effort (slower)

// ============================================================
// FIXED HARNESS — do not modify below this line
// ============================================================

static std::vector<uint8_t> read_file(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) { perror(path); exit(1); }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    rewind(f);
    std::vector<uint8_t> data(sz);
    if ((long)fread(data.data(), 1, sz, f) != sz) { perror("fread"); exit(1); }
    fclose(f);
    return data;
}

static void write_file(const char* path, const std::vector<uint8_t>& data) {
    FILE* f = fopen(path, "wb");
    if (!f) { perror(path); exit(1); }
    fwrite(data.data(), 1, data.size(), f);
    fclose(f);
}

static std::vector<uint8_t> do_compress(const std::vector<uint8_t>& in) {
    lzma_options_lzma opts;
    lzma_lzma_preset(&opts, LEVEL | (EXTREME ? LZMA_PRESET_EXTREME : 0u));
    opts.dict_size = DICT_SIZE;
    opts.lc = LC; opts.lp = LP; opts.pb = PB;

    lzma_filter filters[] = {
        { LZMA_FILTER_LZMA2, &opts },
        { LZMA_VLI_UNKNOWN, nullptr }
    };

    // Prepend 8-byte original-size header so decompressor knows output size.
    size_t bound = lzma_stream_buffer_bound(in.size());
    std::vector<uint8_t> out(8 + bound);
    uint64_t orig = (uint64_t)in.size();
    memcpy(out.data(), &orig, 8);

    size_t out_pos = 0;
    lzma_ret r = lzma_stream_buffer_encode(
        filters, LZMA_CHECK_NONE, nullptr,
        in.data(), in.size(),
        out.data() + 8, &out_pos, bound);
    if (r != LZMA_OK) { fprintf(stderr, "lzma encode error: %d\n", (int)r); exit(1); }
    out.resize(8 + out_pos);
    return out;
}

static std::vector<uint8_t> do_decompress(const std::vector<uint8_t>& in) {
    if (in.size() < 8) { fprintf(stderr, "bad compressed stream\n"); exit(1); }
    uint64_t orig;
    memcpy(&orig, in.data(), 8);
    std::vector<uint8_t> out(orig);
    uint64_t mem = UINT64_MAX;
    size_t in_pos = 0, out_pos = 0;
    lzma_ret r = lzma_stream_buffer_decode(
        &mem, 0, nullptr,
        in.data() + 8, &in_pos, in.size() - 8,
        out.data(), &out_pos, orig);
    if (r != LZMA_OK || out_pos != orig) {
        fprintf(stderr, "lzma decode error: %d\n", (int)r); exit(1);
    }
    return out;
}

int main(int argc, char* argv[]) {
    if (argc != 4 || (argv[1][0] != 'c' && argv[1][0] != 'd')) {
        fprintf(stderr, "usage: %s c|d <input> <output>\n", argv[0]);
        return 1;
    }
    auto data = read_file(argv[2]);
    auto result = (argv[1][0] == 'c') ? do_compress(data) : do_decompress(data);
    write_file(argv[3], result);
    return 0;
}
