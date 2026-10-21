export type Version = 'source' | 'working';
export type Block = {id:string; tag:string; top:number};
export type Layout = {blocks:Block[]; extent:number};

// Keep matches monotonic. IDs survive translation; positional fallback is only
// safe inside equally sized gaps between known anchors.
export function alignLayouts(source:Layout, working:Layout) {
  const a=source.blocks, b=working.blocks;
  const unique = (blocks:Block[]) => {
    const ids=new Map<string,number>();
    blocks.forEach((block,i)=>{if(block.id)ids.set(block.id,ids.has(block.id)?-1:i);});
    return ids;
  };
  const ai=unique(a), bi=unique(b), anchors:[number,number][]=[];
  let last=-1;
  a.forEach((block,i)=>{
    const j=bi.get(block.id);
    if(block.id && ai.get(block.id)===i && j!==undefined && j>last){anchors.push([i,j]);last=j;}
  });
  const pairs:[number,number][]=[], boundaries:[number,number][]=[[-1,-1],...anchors,[a.length,b.length]];
  let positional=false;
  for(let k=1;k<boundaries.length;k++) {
    const [i0,j0]=boundaries[k-1], [i1,j1]=boundaries[k];
    if(i1-i0===j1-j0) {
      const gap:[number,number][]=[];
      for(let d=1;d<i1-i0;d++) {
        const x=a[i0+d], y=b[j0+d];
        // Different explicit IDs indicate an insertion/deletion, even if the
        // total block count happens to be unchanged.
        if(x.tag!==y.tag || (x.id && y.id && x.id!==y.id)){gap.length=0;break;}
        gap.push([i0+d,j0+d]);
      }
      if(gap.length){pairs.push(...gap);positional=true;}
    }
    if(i1<a.length)pairs.push([i1,j1]);
  }
  const left=new Array(a.length).fill(0), right=new Array(b.length).fill(0);
  let l=0,r=0;
  for(const [i,j] of pairs) {
    const delta=(a[i].top+l)-(b[j].top+r);
    if(delta>0){right[j]=delta;r+=delta;}else{left[i]=-delta;l-=delta;}
  }
  const extent=Math.max(source.extent+l,working.extent+r);
  return {source:{pads:left,end:extent-source.extent-l},working:{pads:right,end:extent-working.extent-r},
    unmatched:a.length+b.length-2*pairs.length,positional};
}
