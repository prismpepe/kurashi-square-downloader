"""Package prepared, sanitized distributions; never package the working directory."""
from pathlib import Path
import argparse, hashlib, zipfile, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from version import VERSION
ROOT=Path(__file__).resolve().parents[1]

def entries(source):
    for p in sorted(source.rglob('*')):
        if not p.is_file(): continue
        rel=p.relative_to(source)
        if '__pycache__' in rel.parts or p.suffix in {'.pyc','.pyo'}:continue
        if (rel.parts[0].lower() == 'data' or any(part.lower() in {'web-profile','.kurashi-downloader','.git'} for part in rel.parts)) or p.name in {'settings.json','login-credentials.json','web-session.json'}:
            raise ValueError('Private or generated data in release input: '+str(rel))
        yield p,rel

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,required=True);parser.add_argument('--python',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    sources={'exe':args.exe,'python':args.python}
    names=[f'KurashiDownloader-{VERSION}-{kind}{suffix}.zip' for kind in sources for suffix in ('','-documents')]
    if any((args.out/name).exists() for name in names):raise FileExistsError('Use a fresh output directory')
    manifests={kind:list(entries(source)) for kind,source in sources.items()}
    hashes=[]
    for kind in sources:
        folder='KurashiDownloader'+('-Python' if kind=='python' else '')
        for suffix in ('','-documents'):
            target=args.out/f'KurashiDownloader-{VERSION}-{kind}{suffix}.zip'
            with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
                if not suffix:
                    for p,rel in manifests[kind]:
                        if rel.as_posix() not in {'LICENSE','THIRD_PARTY_NOTICES.md'}:z.write(p,Path(folder)/rel)
                    for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):z.write(ROOT/name,Path(folder)/name)
                else:
                    base=Path(folder+'-Documents')
                    for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):z.write(ROOT/name,base/name)
                    for p in (ROOT/'docs').glob('*.txt'):
                        text=p.read_text('utf-8-sig')
                        lines=[line for line in text.splitlines() if not line.startswith('Python版：' if kind=='exe' else 'exe版：')]
                        text=f'対象：{kind}版\n'+ '\n'.join(lines)
                        z.writestr(str(base/p.name),text.encode('utf-8-sig'))
                    for p,rel in entries(ROOT/'third_party'):z.write(p,base/'third_party'/rel)
            with zipfile.ZipFile(target) as z:
                if z.testzip() is not None:raise ValueError('Invalid archive')
            hashes.append(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name)
            print(target.name,flush=True)
    (args.out/'SHA256SUMS.txt').write_text('\n'.join(hashes)+'\n','ascii')
if __name__=='__main__':main()
