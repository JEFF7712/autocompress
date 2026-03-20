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
static const uint8_t  ESCAPE    = 0xFF;

struct Token {
    const char* text;
    size_t len;
};

static const Token TOKENS[] = {
    { "<text xml:space=\"preserve\">", sizeof("<text xml:space=\"preserve\">") - 1 },
    { "</contributor>", sizeof("</contributor>") - 1 },
    { "<contributor>", sizeof("<contributor>") - 1 },
    { "</timestamp>", sizeof("</timestamp>") - 1 },
    { "<timestamp>", sizeof("<timestamp>") - 1 },
    { "</revision>", sizeof("</revision>") - 1 },
    { "<revision>", sizeof("<revision>") - 1 },
    { "</username>", sizeof("</username>") - 1 },
    { "<username>", sizeof("<username>") - 1 },
    { "</comment>", sizeof("</comment>") - 1 },
    { "<comment>", sizeof("<comment>") - 1 },
    { "</title>", sizeof("</title>") - 1 },
    { "<title>", sizeof("<title>") - 1 },
    { "</text>", sizeof("</text>") - 1 },
    { "<minor />", sizeof("<minor />") - 1 },
    { "</page>", sizeof("</page>") - 1 },
    { "<page>", sizeof("<page>") - 1 },
    { "</id>", sizeof("</id>") - 1 },
    { "<id>", sizeof("<id>") - 1 },
    { "</ip>", sizeof("</ip>") - 1 },
    { "<ip>", sizeof("<ip>") - 1 },
};

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

static std::vector<uint8_t> preprocess(const std::vector<uint8_t>& in) {
    std::vector<uint8_t> out;
    out.reserve(in.size());

    for (size_t i = 0; i < in.size();) {
        if (in[i] == ESCAPE) {
            out.push_back(ESCAPE);
            out.push_back(0);
            ++i;
            continue;
        }

        bool matched = false;
        for (size_t token_idx = 0; token_idx < sizeof(TOKENS) / sizeof(TOKENS[0]); ++token_idx) {
            const Token& token = TOKENS[token_idx];
            if (i + token.len <= in.size()
                && memcmp(in.data() + i, token.text, token.len) == 0) {
                out.push_back(ESCAPE);
                out.push_back((uint8_t)(token_idx + 1));
                i += token.len;
                matched = true;
                break;
            }
        }

        if (!matched) {
            out.push_back(in[i]);
            ++i;
        }
    }

    return out;
}

static std::vector<uint8_t> postprocess(const std::vector<uint8_t>& in, uint64_t orig_size) {
    std::vector<uint8_t> out;
    out.reserve(orig_size);

    for (size_t i = 0; i < in.size(); ++i) {
        if (in[i] != ESCAPE) {
            out.push_back(in[i]);
            continue;
        }

        if (++i >= in.size()) { fprintf(stderr, "bad token stream\n"); exit(1); }
        uint8_t code = in[i];
        if (code == 0) {
            out.push_back(ESCAPE);
            continue;
        }

        if (code > sizeof(TOKENS) / sizeof(TOKENS[0])) {
            fprintf(stderr, "bad token code\n");
            exit(1);
        }

        const Token& token = TOKENS[code - 1];
        out.insert(out.end(), token.text, token.text + token.len);
    }

    if (out.size() != orig_size) {
        fprintf(stderr, "postprocess size mismatch\n");
        exit(1);
    }
    return out;
}

static std::vector<uint8_t> do_compress(const std::vector<uint8_t>& in) {
    auto pre = preprocess(in);
    lzma_options_lzma opts;
    lzma_lzma_preset(&opts, LEVEL | (EXTREME ? LZMA_PRESET_EXTREME : 0u));
    opts.dict_size = DICT_SIZE;
    opts.lc = LC; opts.lp = LP; opts.pb = PB;

    lzma_filter filters[] = {
        { LZMA_FILTER_LZMA1, &opts },
        { LZMA_VLI_UNKNOWN, nullptr }
    };

    // Prepend original and transformed sizes so the decoder can reverse preprocessing.
    size_t bound = lzma_stream_buffer_bound(pre.size());
    std::vector<uint8_t> out(16 + bound);
    uint64_t orig = (uint64_t)in.size();
    uint64_t pre_size = (uint64_t)pre.size();
    memcpy(out.data(), &orig, 8);
    memcpy(out.data() + 8, &pre_size, 8);

    size_t out_pos = 0;
    lzma_ret r = lzma_raw_buffer_encode(
        filters, nullptr,
        pre.data(), pre.size(),
        out.data() + 16, &out_pos, bound);
    if (r != LZMA_OK) { fprintf(stderr, "lzma encode error: %d\n", (int)r); exit(1); }
    out.resize(16 + out_pos);
    return out;
}

static std::vector<uint8_t> do_decompress(const std::vector<uint8_t>& in) {
    if (in.size() < 16) { fprintf(stderr, "bad compressed stream\n"); exit(1); }
    lzma_options_lzma opts;
    lzma_lzma_preset(&opts, LEVEL | (EXTREME ? LZMA_PRESET_EXTREME : 0u));
    opts.dict_size = DICT_SIZE;
    opts.lc = LC; opts.lp = LP; opts.pb = PB;

    lzma_filter filters[] = {
        { LZMA_FILTER_LZMA1, &opts },
        { LZMA_VLI_UNKNOWN, nullptr }
    };

    uint64_t orig;
    uint64_t pre_size;
    memcpy(&orig, in.data(), 8);
    memcpy(&pre_size, in.data() + 8, 8);
    std::vector<uint8_t> pre(pre_size);
    size_t in_pos = 0, out_pos = 0;
    lzma_ret r = lzma_raw_buffer_decode(
        filters, nullptr,
        in.data() + 16, &in_pos, in.size() - 16,
        pre.data(), &out_pos, pre_size);
    if (r != LZMA_OK || in_pos != in.size() - 16 || out_pos != pre_size) {
        fprintf(stderr, "lzma decode error: %d\n", (int)r); exit(1);
    }
    return postprocess(pre, orig);
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
