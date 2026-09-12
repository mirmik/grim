import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from server.app import create_app, safe_file
from server.library import Library


def make_book(root, title='Test', text='First'):
    root.mkdir()
    (root / 'one.html').write_text(f'<html><head></head><body><p id="p">{text}</p></body></html>')
    (root / 'book.json').write_text(json.dumps({'title':title,'pages':[{'id':'one','title':'One','path':'one.html'}]}))
    return root

@pytest.fixture
def book(tmp_path):
    return make_book(tmp_path/'book')

@pytest.fixture
def client(book,tmp_path):
    with TestClient(create_app(book,tmp_path/'library')) as client:
        yield client

def entry(client):
    return client.get('/api/library').json()['books'][0]

def headers(client):
    return {'X-Grim-Viewer':client.get('/api/library').json()['writer_token']}

def info(client,book_id=None):
    return client.get('/api/books/'+(book_id or entry(client)['id']))

def test_book_html_and_download(client):
    book_id=entry(client)['id']
    assert info(client).json()['pages'][0]['id']=='one'
    page=client.get(f'/book/{book_id}/one.html')
    assert '/bridge.js' in page.text
    assert 'sandbox allow-scripts' in page.headers['content-security-policy']
    assert 'allow-same-origin' not in page.headers['content-security-policy']
    assert "connect-src 'none'" in page.headers['content-security-policy']
    download=client.get(f'/book/{book_id}/one.html?download=1')
    assert 'attachment' in download.headers['content-disposition']
    assert download.headers['content-type']=='application/octet-stream'

def test_escape_and_symlink(client,book):
    book_id=entry(client)['id']
    outside=book.parent/'secret.txt';outside.write_text('secret')
    (book/'escape.txt').symlink_to(outside)
    for route in (f'/book/{book_id}/escape.txt',f'/book/{book_id}/%2e%2e/secret.txt',f'/book/{book_id}/%2Fetc/passwd','/book/unknown/one.html','/vendor/%2e%2e/package.json'):
        assert client.get(route).status_code==404
    with pytest.raises(Exception):safe_file(book,'../secret.txt')

def test_create_add_and_restart(client,book,tmp_path):
    hdr=headers(client)
    original_id=entry(client)['id']
    created=client.post('/api/library/create',json={'title':'Empty book'},headers=hdr)
    assert created.status_code==200
    created=created.json();root=Path(created['root'])
    assert root.is_dir() and json.loads((root/'book.json').read_text())['pages']==[]
    second=make_book(tmp_path/'existing','Second','Other')
    before=(second/'one.html').read_bytes()
    added=client.post('/api/library/add',json={'root':str(second)},headers=hdr).json()
    duplicate=client.post('/api/library/add',json={'root':str(second)},headers=hdr).json()
    assert added['id']==duplicate['id']
    assert (second/'one.html').read_bytes()==before
    # A genuinely new app instance reloads the same durable registry and IDs.
    with TestClient(create_app(book,tmp_path/'library')) as restarted:
        found={b['id']:b for b in restarted.get('/api/library').json()['books']}
        assert set(found)=={original_id,created['id'],added['id']}
        assert found[added['id']]['root']==str(second)
        assert restarted.get('/api/context').json()['context'] is None

def test_registration_validation_and_no_writes_without_token(client,tmp_path):
    for endpoint,data in (('create',{'title':'Denied'}),('add',{'root':str(tmp_path)})):
        assert client.post('/api/library/'+endpoint,json=data).status_code==403
    count=len(client.get('/api/library').json()['books'])
    for root in ('relative/path',str(tmp_path/'missing'),str(tmp_path)):
        assert client.post('/api/library/add',json={'root':root},headers=headers(client)).status_code==422
    assert client.post('/api/library/create',json={'title':'   '},headers=headers(client)).status_code==422
    assert len(client.get('/api/library').json()['books'])==count

def test_two_books_readers_and_late_context(client,tmp_path):
    one=entry(client);hdr=headers(client)
    second=make_book(tmp_path/'second','Second','Other')
    two=client.post('/api/library/add',json={'root':str(second)},headers=hdr).json()
    payload={'reader_id':'reader-a','sequence':1,'book_id':one['id'],'page_id':'one','selection':'First','visible_text':'First','anchor':'p','scroll_y':22}
    assert client.post('/api/viewer/context',json=payload,headers=hdr).status_code==200
    assert client.post('/api/viewer/context',json={**payload,'reader_id':'reader-b','book_id':two['id'],'selection':'Other'},headers=hdr).status_code==200
    a=client.get('/api/context?reader_id=reader-a').json()['context']
    b=client.get('/api/context?reader_id=reader-b').json()['context']
    assert a['book']['id']==one['id'] and a['book']['root']==one['root']
    assert b['book']['id']==two['id'] and b['selection']=='Other'
    assert client.get(f"/api/context?reader_id=reader-a&book_id={two['id']}").json()['context'] is None
    assert len(client.get(f"/api/context?book_id={one['id']}").json()['readers'])==1
    # Rapid switch in one reader: an old in-flight update must not win.
    client.post('/api/viewer/context',json={**payload,'sequence':3,'book_id':two['id']},headers=hdr)
    late=client.post('/api/viewer/context',json={**payload,'sequence':2},headers=hdr).json()
    assert late['ignored']
    assert client.get('/api/context?reader_id=reader-a').json()['context']['book']['id']==two['id']
    client.post('/api/viewer/idle',json={'reader_id':'reader-a','sequence':4},headers=hdr)
    client.post('/api/viewer/context',json={**payload,'sequence':3},headers=hdr)
    assert client.get('/api/context?reader_id=reader-a').json()['context'] is None
    assert client.post('/api/viewer/context',json={**payload,'sequence':5,'page_id':'missing'},headers=hdr).status_code==404
    assert client.post('/api/context',json=payload).status_code==405

def test_empty_book_context(client):
    hdr=headers(client);book=client.post('/api/library/create',json={'title':'Blank'},headers=hdr).json()
    assert client.post('/api/viewer/context',json={'reader_id':'blank','sequence':1,'book_id':book['id'],'page_id':None},headers=hdr).status_code==200
    result=client.get('/api/context').json()['context']
    assert result['book']['root']==book['root'] and result['page'] is None

@pytest.mark.parametrize('hdr',[{'Origin':'null'},{'Origin':'https://evil.example'},{'Sec-Fetch-Site':'cross-site'},{'Sec-Fetch-Site':'same-site'},{'Host':'attacker.example'}])
def test_api_boundary(client,hdr):
    assert client.get('/api/context',headers=hdr).status_code==403
    assert client.get('/api/library',headers=hdr).status_code==403
    # Even a stolen token is not sufficient for a foreign browser origin.
    assert client.post('/api/library/create',json={'title':'Denied'},headers={**headers(client),**hdr}).status_code==403

def test_watcher_is_per_book(client,book,tmp_path):
    hdr=headers(client)
    second=make_book(tmp_path/'second','Second','Other')
    two=client.post('/api/library/add',json={'root':str(second)},headers=hdr).json()
    before=info(client).json()['revision'];other_before=info(client,two['id']).json()['revision']
    (book/'one.html').write_text('<html><head></head><p>Changed</p></html>')
    for _ in range(30):
        if info(client).json()['revision']>before:break
        time.sleep(.1)
    assert info(client).json()['revision']>before
    assert info(client,two['id']).json()['revision']==other_before
    assert 'Changed' in client.get(f"/book/{entry(client)['id']}/one.html").text
    assert 'Other' in client.get(f"/book/{two['id']}/one.html").text

def test_invalid_manifest_stays_in_library(client,book):
    book_id=entry(client)['id'];(book/'book.json').write_text('{')
    assert info(client,book_id).status_code==422
    assert entry(client)['id']==book_id and entry(client)['error']

def test_corrupt_registry_is_not_overwritten(tmp_path):
    directory=tmp_path/'broken';directory.mkdir();registry=directory/'library.json';registry.write_text('{broken')
    with pytest.raises(ValueError):Library(directory,[])
    assert registry.read_text()=='{broken'
