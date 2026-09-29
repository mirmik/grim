(() => {
  let ready = false, timer, noteRanges = new Map();
  const send = (type, payload = {}) => parent.postMessage({grim: true, type, path: location.pathname, ...payload}, '*');
  // A sandboxed book cannot read the viewer's storage or DOM. The viewer sends
  // its resolved theme through the same source-checked channel as restoration.
  const themeStyle = document.createElement('style');
  themeStyle.textContent = `
    html[data-grim-theme="light"] { color-scheme: light; }
    html[data-grim-theme="dark"] { color-scheme: dark; background: #17211d !important; color: #e0e9df !important; }
    html[data-grim-theme="dark"] :where(body, body *):not(:where(img, picture, video, audio, canvas, svg, svg *, [data-grim-preserve-colors], [data-grim-preserve-colors] *)) {
      color: #e0e9df !important;
      background-color: transparent !important;
      border-color: #49614d !important;
    }
    html[data-grim-theme="dark"] :where(pre, code, blockquote, .note, .formula, .lab, th, input, textarea, select, button):not([data-grim-preserve-colors], [data-grim-preserve-colors] *) { background-color: #233329 !important; }
    html[data-grim-theme="dark"] :where(a, a *):not([data-grim-preserve-colors], [data-grim-preserve-colors] *, svg, svg *) { color: #a8d299 !important; }
    html[data-grim-theme="dark"] :where(figcaption, .eyebrow, .lead, .small):not([data-grim-preserve-colors], [data-grim-preserve-colors] *) { color: #a8b8aa !important; }
    /* Transparent diagrams often contain dark labels. Keep a light backing,
       without inverting the colors of illustrations or interactive canvases. */
    html[data-grim-theme="dark"] :where(svg, canvas):not([data-grim-preserve-colors], [data-grim-preserve-colors] *) { background-color: #fffefa; }
  `;
  document.documentElement.append(themeStyle);
  function applyTheme(theme) {
    if (theme !== 'light' && theme !== 'dark') return;
    document.documentElement.dataset.grimTheme = theme;
  }
  // Apply before body parsing, including on page changes; later updates arrive
  // by message so controls, selection and scroll position stay intact.
  applyTheme(new URLSearchParams(location.search).get('grim-theme'));
  const blockSelector = 'h1,h2,h3,p,li,figcaption,blockquote,pre,math,.katex';
  const blocks = () => {
    const visible = [...document.querySelectorAll(blockSelector)].filter(el => {
      const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.width > 0 && r.height > 0;
    });
    const included = new Set(visible);
    return visible.filter(el => {
      for (let p = el.parentElement; p; p = p.parentElement) if (included.has(p)) return false;
      return true;
    });
  };
  function readingText(node, range) {
    if (range && !range.intersectsNode(node)) return '';
    if (node.nodeType === Node.TEXT_NODE) {
      const start = range?.startContainer === node ? range.startOffset : 0;
      const end = range?.endContainer === node ? range.endOffset : node.length;
      return node.data.slice(start, end);
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return '';
    if (node.matches('script,style,annotation,annotation-xml')) return '';
    if (node.matches('.katex')) {
      // KaTeX includes MathML, its TeX annotation, and visual HTML for one formula.
      const visual = node.querySelector('.katex-html');
      const source = node.querySelector('annotation[encoding="application/x-tex"]');
      if (!range && source) return source.textContent;
      if (visual) {
        const walker = document.createTreeWalker(visual, NodeFilter.SHOW_TEXT);
        const first = walker.nextNode();
        let last = first;
        while (walker.nextNode()) last = walker.currentNode;
        if (source && first && range.comparePoint(first, 0) === 0 && range.comparePoint(last, last.length) === 0) return source.textContent;
        // A selection can begin/end inside a formula: keep just its selected glyphs.
        return readingText(visual, range);
      }
    }
    if (node.matches('br')) return '\n';
    const text = [...node.childNodes].map(child => readingText(child, range)).join('');
    return node.matches('h1,h2,h3,p,li,figcaption,blockquote,pre,div') ? '\n' + text + '\n' : text;
  }
  function selectionText() {
    const selection = getSelection();
    if (!selection || selection.isCollapsed) return '';
    return Array.from({length: selection.rangeCount}, (_, i) => readingText(document.body, selection.getRangeAt(i)).replace(/^\n+|\n+$/g, '')).join('\n');
  }
  function selectionRect() {
    const selection=getSelection();
    if(!selection || selection.isCollapsed || !selection.rangeCount)return null;
    const rect=selection.getRangeAt(0).getBoundingClientRect();
    return {left:rect.left,top:rect.top,bottom:rect.bottom,width:rect.width};
  }
  const normalize = value => value.replace(/\s+/g, ' ').trim();
  let pageCharacters = 0, pageTextDirty = true;
  const pageTextObserver = new MutationObserver(() => {pageTextDirty = true; schedule();});
  const excluded = node => node.parentElement?.closest('script,style,annotation,annotation-xml,[aria-hidden="true"]');
  function plainText(node, range) {
    if (range && !range.intersectsNode(node)) return '';
    if (node.nodeType === Node.TEXT_NODE) {
      if (excluded(node)) return '';
      const start = range?.startContainer === node ? range.startOffset : 0;
      const end = range?.endContainer === node ? range.endOffset : node.length;
      return node.data.slice(start, end);
    }
    if (node.nodeType !== Node.ELEMENT_NODE || node.matches('script,style,annotation,annotation-xml,[aria-hidden="true"]')) return '';
    return [...node.childNodes].map(child => plainText(child, range)).join('');
  }
  function textModel(root) {
    const chars = [], parts = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {acceptNode: node => excluded(node) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
    let node;
    while ((node = walker.nextNode())) {
      for (let i=0;i<node.data.length;i++) {
        const whitespace = /\s/.test(node.data[i]);
        if (whitespace && (!parts.length || parts[parts.length-1] === ' ')) continue;
        parts.push(whitespace ? ' ' : node.data[i]);
        chars.push({node,start:i,end:i+1});
      }
    }
    if (parts[0] === ' ') {parts.shift();chars.shift();}
    if (parts[parts.length-1] === ' ') {parts.pop();chars.pop();}
    return {text:parts.join(''),chars};
  }
  function rangeFrom(model, start, end) {
    if (start < 0 || end <= start || end > model.chars.length) return null;
    const first=model.chars[start],last=model.chars[end-1],range=document.createRange();
    range.setStart(first.node,first.start);range.setEnd(last.node,last.end);return range;
  }
  function selectionAnchor() {
    const selection=getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
    const range=selection.getRangeAt(0), startElement=range.startContainer.nodeType===Node.ELEMENT_NODE?range.startContainer:range.startContainer.parentElement;
    const semantic=startElement?.closest(blockSelector), identified=startElement?.closest('[id]');
    let block=(semantic?.id&&semantic) || (identified?.contains(range.endContainer)&&identified) || semantic || document.body;
    if (!block.contains(range.endContainer)) block=document.body;
    const model=textModel(block), exact=normalize(plainText(block,range)).slice(0,12000);
    if (!exact) return null;
    const before=document.createRange();before.selectNodeContents(block);before.setEnd(range.startContainer,range.startOffset);
    const guess=normalize(plainText(block,before)).length;
    const matches=[];for(let at=model.text.indexOf(exact);at>=0;at=model.text.indexOf(exact,at+1))matches.push(at);
    const start=matches.length?matches.reduce((best,at)=>Math.abs(at-guess)<Math.abs(best-guess)?at:best,matches[0]):Math.min(guess,Math.max(0,model.text.length-exact.length));
    const end=Math.min(model.text.length,start+exact.length);
    return {exact,prefix:model.text.slice(Math.max(0,start-120),start),suffix:model.text.slice(end,end+120),element_id:block.id||'',block_text:model.text.slice(0,24000),start,end};
  }
  function occurrences(text, needle) {
    const result=[];if(!needle)return result;
    for(let at=text.indexOf(needle);at>=0;at=text.indexOf(needle,at+1))result.push(at);
    return result;
  }
  function bestExact(model, anchor) {
    const places=occurrences(model.text,anchor.exact);if(!places.length)return null;
    let best=places[0],score=-Infinity;
    for(const at of places) {
      const before=model.text.slice(Math.max(0,at-anchor.prefix.length),at),after=model.text.slice(at+anchor.exact.length,at+anchor.exact.length+anchor.suffix.length);
      let next=(anchor.prefix&&before.endsWith(anchor.prefix)?4:0)+(anchor.suffix&&after.startsWith(anchor.suffix)?4:0)-Math.abs(at-anchor.start)/Math.max(1,model.text.length);
      if(next>score){score=next;best=at;}
    }
    return rangeFrom(model,best,best+anchor.exact.length);
  }
  function resolve(anchor) {
    const element=anchor.element_id&&document.getElementById(anchor.element_id),root=element||document.body,model=textModel(root);
    let range=bestExact(model,anchor);if(range)return {range,kind:'exact'};
    if (!element || !model.text) return null;
    const oldLength=Math.max(1,anchor.block_text.length),prefix=anchor.prefix.slice(-80),suffix=anchor.suffix.slice(0,80);
    let start=prefix?model.text.indexOf(prefix):-1,end=suffix?model.text.indexOf(suffix):-1;
    start=start>=0?start+prefix.length:Math.round(anchor.start/oldLength*model.text.length);
    end=end>=start?end:Math.round((anchor.end/oldLength)*model.text.length);
    if(!anchor.suffix && anchor.end>=oldLength-1)end=model.text.length;
    start=Math.max(0,Math.min(start,model.text.length-1));end=Math.max(start+1,Math.min(end,model.text.length));
    range=rangeFrom(model,start,end);return range?{range,kind:'adapted'}:null;
  }
  function renderNotes(notes) {
    noteRanges=new Map();const ranges=[],resolved={},missing=[];
    for(const note of Array.isArray(notes)?notes:[]) {
      const found=note?.anchor&&resolve(note.anchor);
      if(found){noteRanges.set(note.id,found.range);ranges.push(found.range);resolved[note.id]=found.kind;}else missing.push(note?.id);
    }
    if (CSS.highlights) CSS.highlights.set('grim-notes',new Highlight(...ranges));
    document.documentElement.dataset.grimNotesResolved=String(ranges.length);
    send('notes-status',{resolved,missing});
  }
  function focusNote(note) {
    const found=noteRanges.get(note?.id) || (note?.anchor&&resolve(note.anchor)?.range);
    if(!found)return;
    const target=found.startContainer.parentElement;target?.scrollIntoView({block:'center',behavior:'smooth'});
    if(CSS.highlights){CSS.highlights.set('grim-note-focus',new Highlight(found));setTimeout(()=>CSS.highlights.delete('grim-note-focus'),1400);}
  }
  function report() {
    if (!ready) return;
    if (pageTextDirty) {
      pageCharacters = Array.from(normalize(readingText(document.body))).length;
      pageTextDirty = false;
    }
    const visible = blocks();
    const anchor = visible.find(el => el.id);
    send('context', {page_characters: pageCharacters, visible_text: visible.map(el => readingText(el).trim()).join('\n').slice(0,24000), selection: selectionText().slice(0,12000), selection_anchor: selectionAnchor(), selection_rect: selectionRect(), anchor: anchor?.id || '', anchor_offset: anchor?.getBoundingClientRect().top || 0, scroll_y: Math.max(0,scrollY)});
  }
  function schedule() {clearTimeout(timer); timer = setTimeout(report, 100);}
  function selectionFinished() {
    // Mobile selection handles often update after touchend/pointerup. Report
    // both shortly after the gesture and once the native toolbar has settled.
    schedule();setTimeout(report,350);setTimeout(report,900);
  }
  addEventListener('message', event => {
    if (event.source !== parent || !event.data?.grim) return;
    if (event.data.type === 'theme') { applyTheme(event.data.theme); return; }
    if(event.data.type==='restore') {
      const p = event.data.position;
      if (p) {
        const anchor = p.anchor && document.getElementById(p.anchor);
        scrollTo(0, anchor ? scrollY + anchor.getBoundingClientRect().top - p.anchor_offset : p.scroll_y || 0);
      }
      ready = true; report();
    } else if(event.data.type==='notes') renderNotes(event.data.notes);
    else if(event.data.type==='focus-note') focusNote(event.data.note);
    else if(event.data.type==='clear-selection') {getSelection()?.removeAllRanges();report();}
  });
  addEventListener('load', () => {
    pageTextObserver.observe(document.body, {childList:true, characterData:true, subtree:true});
    send('ready');
  });
  addEventListener('scroll', schedule, {passive:true});
  addEventListener('resize', schedule);
  document.addEventListener('selectionchange', schedule);
  document.addEventListener('pointerup',selectionFinished,{passive:true});
  document.addEventListener('touchend',selectionFinished,{passive:true});
  document.addEventListener('keyup',selectionFinished);
  const style=document.createElement('style');style.textContent='::highlight(grim-notes){background:#e6d98f99;text-decoration:underline;text-decoration-color:#a58c35}::highlight(grim-note-focus){background:#e8bd55cc}';document.documentElement.append(style);
  setInterval(report, 10000);
  document.addEventListener('click', event => {
    const a = event.target.closest?.('a[href]');
    if (!a) return;
    const url = new URL(a.href, location.href);
    if (a.hasAttribute('download') && url.origin === location.origin && (url.pathname.startsWith('/book/') || url.pathname.startsWith('/book-source/'))) {
      event.preventDefault(); send('download', {href: url.pathname});
    } else if (url.origin === location.origin && (url.pathname.startsWith('/book/') || url.pathname.startsWith('/book-source/')) && /\.html?$/i.test(url.pathname)) {
      event.preventDefault();
      // Capture the click-time position, not the last throttled scroll report.
      // The parent owns both same-page and cross-page return history.
      report();
      send('navigate', {href:url.pathname + url.hash});
    } else if (url.protocol !== 'http:' && url.protocol !== 'https:' || !a.hasAttribute('download')) {
      event.preventDefault();
    }
  });
})();
