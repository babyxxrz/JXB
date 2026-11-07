from pathlib import Path
root = Path(__file__).resolve().parent
text = "train: " + (root/'prepared/train/images').as_posix() + "\n"
text += "val: " + (root/'prepared/valid/images').as_posix() + "\n"
text += "test: " + (root/'prepared/test/images').as_posix() + "\n"
text += "nc: 4\nnames: [Blue, Green, Red, Yellow]\n"
(root/'data.local.yaml').write_text(text, encoding='utf-8')
print(root/'data.local.yaml')
