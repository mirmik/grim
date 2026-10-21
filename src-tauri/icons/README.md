# Grim icon

`grimoire-source.png` is the original transparent grimoire artwork, generated
with the built-in imagegen tool. The exact prompt is in `grimoire-prompt.txt`.

Regenerate the application icon, web favicon and Android launcher resources:

```sh
npm run icons
```

The script uses the installed Tauri CLI. It preserves the source image and
adds transparent margins for Android's adaptive icon masks. The launcher
background is cream (`#f1efd9`); the complete book fits inside Android's
central 66dp safe circle. Desktop and web icons retain transparency.
