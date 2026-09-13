(() => {
  let ready = false, timer;
  const send = (type, payload = {}) => parent.postMessage({grim: true, type, path: location.pathname, ...payload}, '*');
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
    if (event.source !== parent || !event.data?.grim || event.data.type !== 'restore') return;
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
