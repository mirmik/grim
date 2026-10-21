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
       without inverting illustrations. KaTeX SVGs are inline glyphs (roots,
       arrows, braces): a backing would obscure the adjacent formula text. */
    html[data-grim-theme="dark"] :where(svg, canvas):not(.katex *, [data-grim-preserve-colors], [data-grim-preserve-colors] *) { background-color: #fffefa; }
  `;
  document.documentElement.append(themeStyle);
  function applyTheme(theme) {
    if (theme !== 'light' && theme !== 'dark') return;
    document.documentElement.dataset.grimTheme = theme;
  }
  // Apply before body parsing, including on page changes; later updates arrive
  // by message so controls, selection and scroll position stay intact.
  applyTheme(new URLSearchParams(location.search).get('grim-theme'));
  // Apply reader typography inside the sandbox, rather than scaling the iframe
  // (which would also shrink controls, diagrams and video). Desktop keeps the
  // author's typography until the reader explicitly chooses a size.
  const readingStyle = document.createElement('style');
  document.documentElement.append(readingStyle);
  function applyReadingStyle(size) {
    if (size !== 'auto' && ![14,15,16,17,18,20,22,24].includes(size)) return;
    const anchor = ready ? blocks().find(el => el.id) : null;
    const offset = anchor?.getBoundingClientRect().top;
    const prose = `body { font-size:inherit !important; line-height:1.6 !important; }
      :where(p, li, blockquote):not(:where(.eyebrow, .small, .label, figure *, .formula *, .equation *, .lab *)) { font-size:1rem !important; line-height:1.6 !important; }`;
    readingStyle.textContent = `
      ${size === 'auto' ? '' : `html { font-size:${size}px !important; } ${prose}`}
      @media(max-width:720px),(max-height:500px) and (pointer:coarse) {
        html { font-size:${size === 'auto' ? 16 : size}px !important; -webkit-text-size-adjust:100%; text-size-adjust:100%; }
        ${prose}
        body { padding:12px 16px 24px !important; }
        h1 { font-size:1.75rem !important; line-height:1.2 !important; margin:12px 0 20px !important; }
        h2 { font-size:1.4rem !important; line-height:1.3 !important; margin:28px 0 12px !important; }
        h3 { font-size:1.15rem !important; line-height:1.4 !important; margin:22px 0 10px !important; }
        p { margin-top:.8em !important; margin-bottom:.8em !important; }
        :where(.note, .formula, .equation, .lab) { padding:12px !important; margin:18px 0 !important; }
        :where(img, video) { max-width:100%; height:auto; }
        :where(pre, .formula, .equation, .table-wrap) { overflow-x:auto; }
      }`;
    if (anchor) scrollTo(0, scrollY + anchor.getBoundingClientRect().top - offset);
    schedule();
  }
  applyReadingStyle('auto');
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
    const localAnchor=anchor||visible[0];
    send('context', {page_characters: pageCharacters, visible_text: visible.map(el => readingText(el).trim()).join('\n').slice(0,24000), selection: selectionText().slice(0,12000), selection_anchor: selectionAnchor(), selection_rect: selectionRect(), anchor: anchor?.id || '', block_index:localAnchor?[...document.querySelectorAll(blockSelector)].indexOf(localAnchor):-1, anchor_offset: localAnchor?.getBoundingClientRect().top || 0, scroll_y: Math.max(0,scrollY)});
  }
  function schedule() {clearTimeout(timer); timer = setTimeout(report, 100);}
  function selectionFinished() {
    // Mobile selection handles often update after touchend/pointerup. Report
    // both shortly after the gesture and once the native toolbar has settled.
    schedule();setTimeout(report,350);setTimeout(report,900);
  }
  // Comparison is a presentation only: spacers live in the sandbox DOM and
  // never enter book files, text anchors, notes or the agent's reading text.
  let parallel=false, alignmentBlocks=[], alignmentSpacers=[], alignmentEnd, layoutTimer;
  const alignmentSelector='h1,h2,h3,h4,h5,h6,p,li,blockquote,pre,figure,table';
  const alignmentStyle=document.createElement('style');
  alignmentStyle.textContent='[data-grim-alignment-spacer]{display:flow-root!important;box-sizing:content-box!important;height:0;margin:0!important;padding:0!important;padding-top:1px!important;border:0!important;pointer-events:none!important;overflow:hidden!important;overflow-anchor:none!important} html[data-grim-parallel]{scroll-behavior:auto!important;overflow-anchor:none}';
  document.documentElement.append(alignmentStyle);
  const layoutObserver=new ResizeObserver(()=>scheduleLayout());
  const alignmentObserver=new MutationObserver(()=>{if(parallel){scanAlignment();scheduleLayout();}});
  function spacer() {
    const el=document.createElement('div');el.setAttribute('data-grim-alignment-spacer','');el.setAttribute('aria-hidden','true');return el;
  }
  function scanAlignment() {
    alignmentObserver.disconnect();layoutObserver.disconnect();
    const candidates=[...document.querySelectorAll(alignmentSelector)].filter(el=>!el.closest('[hidden],script,style,[aria-hidden="true"]') && el.getBoundingClientRect().height>0);
    const included=new Set(candidates);
    const next=candidates.filter(el=>{
      for(let p=el.parentElement;p;p=p.parentElement)if(included.has(p))return false;
      return true;
    }).slice(0,10000);
    if(next.length!==alignmentBlocks.length || next.some((el,i)=>el!==alignmentBlocks[i])) {
      alignmentSpacers.forEach(el=>el.remove());alignmentEnd?.remove();
      alignmentBlocks=next;alignmentSpacers=next.map(el=>{const pad=spacer();el.before(pad);return pad;});
      alignmentEnd=spacer();document.body.append(alignmentEnd);
    }
    alignmentBlocks.forEach(el=>layoutObserver.observe(el));
    // Container widths and images affect wrapping even without text edits.
    layoutObserver.observe(document.body);
    alignmentObserver.observe(document.body,{childList:true,characterData:true,subtree:true});
  }
  function scheduleLayout() {clearTimeout(layoutTimer);if(parallel)layoutTimer=setTimeout(reportLayout,60);}
  function reportLayout() {
    if(!parallel)return;
    let padding=0;
    const metrics=alignmentBlocks.map((el,i)=>{
      // Use the rendered height, not the style's decimal string: subpixel
      // rounding otherwise feeds tiny errors back into every subsequent pass.
      padding+=alignmentSpacers[i].getBoundingClientRect().height-1;
      return {id:el.getAttribute('data-grim-source')||el.id||'',tag:el.tagName.toLowerCase(),top:el.getBoundingClientRect().top+scrollY-padding};
    });
    const extent=document.body.getBoundingClientRect().bottom+scrollY-padding-(alignmentEnd.getBoundingClientRect().height-1);
    send('parallel-layout',{blocks:metrics,extent});
  }
  function activate() {if(parallel)send('activate');}
  document.addEventListener('pointerdown',activate,{passive:true});
  document.addEventListener('wheel',activate,{passive:true});
  document.addEventListener('keydown',activate);
  document.addEventListener('selectionchange',()=>{if(!getSelection()?.isCollapsed)activate();});
  addEventListener('scroll',()=>{if(parallel)send('parallel-scroll',{y:Math.max(0,scrollY)});},{passive:true});
  addEventListener('resize',scheduleLayout);
  document.fonts?.ready.then(scheduleLayout);
  addEventListener('message', event => {
    if (event.source !== parent || !event.data?.grim) return;
    if (event.data.type === 'theme') { applyTheme(event.data.theme); return; }
    if (event.data.type === 'reading-style') { applyReadingStyle(event.data.size); return; }
    if(event.data.type==='parallel-start') {
      parallel=true;document.documentElement.dataset.grimParallel='';scanAlignment();scheduleLayout();return;
    }
    if(event.data.type==='parallel-align' && parallel) {
      const pads=event.data.pads;
      if(!Array.isArray(pads) || pads.length!==alignmentSpacers.length || !pads.every(n=>Number.isFinite(n)&&n>=0) || !Number.isFinite(event.data.end) || event.data.end<0)return;
      alignmentSpacers.forEach((el,i)=>el.style.setProperty('height',pads[i]+'px','important'));
      alignmentEnd.style.setProperty('height',event.data.end+'px','important');schedule();return;
    }
    if(event.data.type==='parallel-sync' && parallel) {send('parallel-scroll',{y:Math.max(0,scrollY)});return;}
    if(event.data.type==='parallel-scroll' && parallel && Number.isFinite(event.data.y)) {scrollTo(0,Math.max(0,event.data.y));return;}
    if(event.data.type==='restore') {
      const p = event.data.position;
      if (p) {
        const anchor = (p.anchor && document.getElementById(p.anchor)) || (Number.isSafeInteger(p.block_index) && p.block_index>=0 && document.querySelectorAll(blockSelector)[p.block_index]);
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
