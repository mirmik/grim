(() => {
  let ready = false, timer;
  const send = (type, payload = {}) => parent.postMessage({grim: true, type, path: location.pathname, ...payload}, '*');
  const blocks = () => [...document.querySelectorAll('h1,h2,h3,p,li,figcaption,blockquote,pre,math')].filter(el => {
    const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.width > 0 && r.height > 0;
  });
  function report() {
    if (!ready) return;
    const visible = blocks();
    const anchor = visible.find(el => el.id);
    send('context', {visible_text: visible.map(el => el.textContent.trim()).join('\n').slice(0,24000), selection: String(getSelection() || '').slice(0,12000), anchor: anchor?.id || '', anchor_offset: anchor?.getBoundingClientRect().top || 0, scroll_y: Math.max(0,scrollY)});
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
