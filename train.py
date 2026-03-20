import argparse,bz2,os,zlib
T=1e6
compress_payload=lambda d:bz2.compress(d) if len(d)>=T else zlib.compress(d,9)
restore_payload=lambda d:bz2.decompress(d) if d[:3]==b'BZh' else zlib.decompress(d)
def compute_score_bytes(a,c):
    if{type(a),type(c)}!={int}: raise TypeError
    return a+c
is_roundtrip_equal=bytes.__eq__
baseline_is_configured=lambda:os.getenv('FX2_CMIX_BIN')
def run_evaluation(m,c):
    c=os.path.expanduser(c or '~/.cache/autoresearch');a=0;o=True
    if m[:1]not in'pf': raise ValueError(m)
    for p in([f'{c}/proxy_slices/head.bin',f'{c}/proxy_slices/mid.bin',f'{c}/proxy_slices/tail.bin']if m=='proxy' else[f'{c}/enwik9']):
        with open(p,'rb') as f: d=f.read()
        z=compress_payload(d);o=o and is_roundtrip_equal(d,restore_payload(z));a+=len(z)
    return a,o
def get_code_bytes(): return os.path.getsize(__file__)
def format_summary(mode,archive_bytes,code_bytes,score_bytes,roundtrip_ok):
    if mode[:1]not in'pf': raise ValueError(mode)
    return f"{'proxy'if mode=='proxy'else'full'}_score_bytes: {score_bytes}\narchive_bytes: {archive_bytes}\ncode_bytes: {code_bytes}\nroundtrip_ok: {'true'if roundtrip_ok else 'false'}"
def main():
    p=argparse.ArgumentParser();p.add_argument('--full',action='store_true');p.add_argument('--cache-dir')
    a=p.parse_args();m='full'if a.full else'proxy';b,o=run_evaluation(m,a.cache_dir);c=get_code_bytes();print(format_summary(m,b,c,compute_score_bytes(b,c),o))
if __name__=='__main__': main()
