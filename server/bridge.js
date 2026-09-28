(() => {
  let ready = false, timer;
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
  function report() {
    if (!ready) return;
    const visible = blocks();
    const anchor = visible.find(el => el.id);
    send('context', {visible_text: visible.map(el => readingText(el).trim()).join('\n').slice(0,24000), selection: selectionText().slice(0,12000), anchor: anchor?.id || '', anchor_offset: anchor?.getBoundingClientRect().top || 0, scroll_y: Math.max(0,scrollY)});
  }
  function schedule() {clearTimeout(timer); timer = setTimeout(report, 100);}
  addEventListener('message', event => {
    if (event.source !== parent || !event.data?.grim) return;
    if (event.data.type === 'theme') { applyTheme(event.data.theme); return; }
    if (event.data.type !== 'restore') return;
    const p = event.data.position;
    if (p) {
      const anchor = p.anchor && document.getElementById(p.anchor);
      scrollTo(0, anchor ? scrollY + anchor.getBoundingClientRect().top - p.anchor_offset : p.scroll_y || 0);
    }
    ready = true; report();
  });
  addEventListener('load', () => send('ready'));
  addEventListener('scroll', schedule, {passive:true});
  addEventListener('resize', schedule);
  document.addEventListener('selectionchange', schedule);
  setInterval(report, 10000);
  document.addEventListener('click', event => {
    const a = event.target.closest?.('a[href]');
    if (!a) return;
    const url = new URL(a.href, location.href);
    if (a.hasAttribute('download') && url.origin === location.origin && url.pathname.startsWith('/book/')) {
      event.preventDefault(); send('download', {href: url.pathname});
    } else if (url.origin === location.origin && url.pathname.startsWith('/book/') && /\.html?$/i.test(url.pathname)) {
      event.preventDefault();
      if (url.pathname === location.pathname && url.hash) {
        document.getElementById(decodeURIComponent(url.hash.slice(1)))?.scrollIntoView(); schedule();
      } else send('navigate', {href:url.pathname + url.hash});
    } else if (url.protocol !== 'http:' && url.protocol !== 'https:' || !a.hasAttribute('download')) {
      event.preventDefault();
    }
  });
})();
