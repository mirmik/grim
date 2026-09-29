"""A generated EPUB with real structure/resources, shared by API and UI tests."""
import io
from pathlib import Path
import sys
import zipfile


def epub_bytes(*, epub2=False, extra=None, paragraphs=36, short_intro=False):
    chapter = '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Chapter</title><link rel="stylesheet" href="styles/book.css" /></head><body><section id="chapter"><h1 id="start">Начало</h1><p id="intro">Первый абзац. <a href="notes.xhtml#note">Сноска</a> <a href="#end">В конец главы</a></p><figure><img src="images/picture.svg" alt="Иллюстрация"/><figcaption>Подпись к рисунку</figcaption></figure><svg xmlns="http://www.w3.org/2000/svg" id="diagram" viewBox="0 0 100 50"><text x="5" y="25">Схема</text></svg><math xmlns="http://www.w3.org/1998/Math/MathML"><mfrac><mi>a</mi><mi>b</mi></mfrac></math><table id="table"><tr><td>Ячейка</td></tr></table>'''
    chapter += ''.join(f'<p id="para-{i}">Абзац {i:03d}. ' + 'Текст для разбиения длинной главы. ' * 24 + '</p>' for i in range(paragraphs))
    chapter += '<h2 id="end">Конец главы</h2><p>Последний абзац. <a href="#intro">Вернуться к началу</a></p></section></body></html>'
    entries = {
        'mimetype': 'application/epub+zip',
        'META-INF/container.xml': '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'OEBPS/package.opf': f'''<package xmlns="http://www.idpf.org/2007/opf" version="{'2.0' if epub2 else '3.0'}"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Проверка EPUB</dc:title><dc:creator>Автор</dc:creator></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="notes" href="notes.xhtml" media-type="application/xhtml+xml"/><item id="css" href="styles/book.css" media-type="text/css"/><item id="picture" href="images/picture.svg" media-type="image/svg+xml"/>{'<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>' if epub2 else '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'}</manifest><spine toc="ncx"><itemref idref="chapter"/></spine></package>''',
        'OEBPS/chapter.xhtml': chapter,
        'OEBPS/notes.xhtml': '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Примечания</title></head><body><h1>Примечания</h1><p id="note">Текст сноски. <a href="chapter.xhtml#intro">Назад к тексту</a></p></body></html>',
        'OEBPS/styles/book.css': 'p { color: rgb(23, 45, 67); } figure { background-image:url("../images/picture.svg"); }',
        'OEBPS/images/picture.svg': '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="60"><rect width="160" height="60" fill="green"/></svg>',
    }
    if epub2:
        entries['OEBPS/toc.ncx'] = '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap><navPoint id="n1"><navLabel><text>Глава из NCX</text></navLabel><content src="chapter.xhtml#start"/></navPoint></navMap></ncx>'
    else:
        entries['OEBPS/nav.xhtml'] = '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Оглавление</title></head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml#start">Глава из оглавления</a><ol><li><a href="chapter.xhtml#end">Конец главы</a></li></ol></li></ol></nav></body></html>'
    if short_intro:
        entries['OEBPS/intro.xhtml'] = '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Введение</title></head><body><h1 id="book-intro">Короткое введение</h1><p>Этот текст должен оставаться на странице с началом главы.</p></body></html>'
        entries['OEBPS/package.opf'] = entries['OEBPS/package.opf'].replace('<manifest>', '<manifest><item id="intro" href="intro.xhtml" media-type="application/xhtml+xml"/>').replace('<spine toc="ncx">', '<spine toc="ncx"><itemref idref="intro"/>')
    entries.update(extra or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return stream.getvalue()


if __name__ == '__main__':
    Path(sys.argv[1]).write_bytes(epub_bytes(short_intro='--short-intro' in sys.argv[2:]))
