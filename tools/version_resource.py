import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from version import VERSION, APP_NAME
numbers = tuple(map(int, VERSION.split('.'))) + (0,)
text = f"VSVersionInfo(ffi=FixedFileInfo(filevers={numbers!r},prodvers={numbers!r},mask=0x3f,flags=0x0,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),kids=[StringFileInfo([StringTable('041104b0',[StringStruct('FileDescription',{APP_NAME!r}),StringStruct('FileVersion',{VERSION!r}),StringStruct('ProductName',{APP_NAME!r}),StringStruct('ProductVersion',{VERSION!r}),StringStruct('OriginalFilename','KurashiDownloader.exe')])]),VarFileInfo([VarStruct('Translation',[1041,1200])])])"
path=Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,'utf-8')
