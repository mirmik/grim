import { test, expect } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';

for (const width of [1440, 390]) {
  test(`return restores same-page and nested cross-page links at ${width}px`, async ({page, request}) => {
    await page.setViewportSize({width, height:900});
    const token=(await (await request.get('/api/library')).json()).writer_token;
    const book=await (await request.post('/api/library/create', {
      headers:{'X-Grim-Viewer':token},data:{title:`Return test ${width}`},
    })).json();
    const head='<html><head><style>body{margin:0;padding:20px}p{margin:0} .gap{height:1400px}</style></head><body>';
    await writeFile(path.join(book.root,'one.html'),head+'<h1>One</h1><div class="gap"></div><p id="origin">Original position <a href="#same-note">Same-page note</a> <a href="two.html#note">Other-page note</a></p><div class="gap"></div><p id="same-note">Same-page footnote</p><div class="gap"></div></body></html>');
    await writeFile(path.join(book.root,'two.html'),head+'<h1>Two</h1><div class="gap"></div><p id="note">Other-page footnote <a href="one.html#same-note">Another note</a></p><div class="gap"></div></body></html>');
    await writeFile(path.join(book.root,'book.json'),JSON.stringify({title:book.title,pages:[
      {id:'one',title:'One',path:'one.html'},{id:'two',title:'Two',path:'two.html'},
    ]}));
    await page.goto(`/?book=${book.id}`);
    const frame=page.frameLocator('iframe');
    const back=page.getByRole('button',{name:'Вернуться',exact:true});
    await expect(frame.locator('#origin')).toBeAttached();
    await expect(back).toHaveCount(0);
    // Click immediately after scrolling: the normal context report is debounced.
    const original=await frame.locator('#origin').evaluate(el=>{
      scrollTo(0,el.getBoundingClientRect().top+scrollY-100);
      const before=scrollY;
      (el.querySelector('a') as HTMLAnchorElement).click();
      return before;
    });
    await expect(frame.locator('#same-note')).toBeInViewport();
    await expect(back).toBeVisible();
    await back.click();
    await expect.poll(()=>frame.locator('body').evaluate(()=>scrollY)).toBeCloseTo(original,0);
    await expect(back).toHaveCount(0);

    await frame.getByRole('link',{name:'Other-page note',exact:true}).click();
    await expect(frame.locator('#note')).toBeInViewport();
    const second=await frame.locator('body').evaluate(()=>scrollY);
    await frame.getByRole('link',{name:'Another note',exact:true}).click();
    await expect(frame.locator('#same-note')).toBeInViewport();
    const box=await back.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x+box!.width).toBeLessThanOrEqual(width);
    await back.click();
    await expect(frame.locator('#note')).toBeInViewport();
    await expect.poll(()=>frame.locator('body').evaluate(()=>scrollY)).toBeCloseTo(second,0);
    await back.click();
    await expect(frame.locator('#origin')).toBeInViewport();
    await expect.poll(()=>frame.locator('body').evaluate(()=>scrollY)).toBeCloseTo(original,0);
    await expect(back).toHaveCount(0);
  });
}
