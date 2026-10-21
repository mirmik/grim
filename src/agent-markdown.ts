import { Marked, Renderer } from 'marked';
import DOMPurify from 'dompurify';

function escape(text:string) {
  return text.replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]!));
}

function link(href:string, label:string, title?:string|null) {
  try {
    const url=new URL(href);
    if(!['https:','http:'].includes(url.protocol)||!url.hostname||url.username||url.password)return label;
    return `<a href="${escape(url.href)}" target="_blank" rel="noopener noreferrer"${title?` title="${escape(title)}"`:''}>${label}</a>`;
  }catch{return label;}
}

const markdown=new Marked({
  gfm:true,
  breaks:true,
  renderer:{
    // Raw HTML remains visible reference text; only the Markdown renderer
    // creates elements. Remote images become links rather than network loads.
    html({text}) {return escape(text);},
    link({href,title,tokens}) {return link(href,this.parser.parseInline(tokens),title);},
    image({href,text}) {return link(href,escape(text?`[Изображение: ${text}]`:'[Изображение]'));},
    checkbox({checked}) {return checked?'☑ ':'☐ ';},
    table(token) {
      return `<div class="agent-table" tabindex="0" aria-label="Таблица с горизонтальной прокруткой">${Renderer.prototype.table.call(this,token)}</div>`;
    },
  },
});

export function renderAgentMarkdown(text:string):string {
  try {
    return DOMPurify.sanitize(markdown.parse(text,{async:false}),{
      ALLOWED_TAGS:['p','br','strong','em','del','blockquote','ul','ol','li','h1','h2','h3','h4','h5','h6',
        'pre','code','hr','a','div','table','thead','tbody','tr','th','td'],
      ALLOWED_ATTR:['href','title','target','rel','start','align','class','tabindex','aria-label'],
      ALLOW_DATA_ATTR:false,
    });
  }catch{
    // An unusual or unfinished answer must remain readable if parsing fails.
    return `<p>${escape(text).replace(/\n/g,'<br>')}</p>`;
  }
}
