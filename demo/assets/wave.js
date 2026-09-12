const amplitude = document.getElementById('amplitude');
const frequency = document.getElementById('frequency');
const canvas = document.getElementById('wave');
function draw() {
  const a=Number(amplitude.value), f=Number(frequency.value);
  document.getElementById('a-value').textContent=a.toFixed(1);
  document.getElementById('f-value').textContent=f.toFixed(1)+' Гц';
  const w=canvas.clientWidth, h=210, d=devicePixelRatio||1;
  canvas.width=w*d; canvas.height=h*d;
  const c=canvas.getContext('2d'); c.scale(d,d);c.clearRect(0,0,w,h);
  c.strokeStyle='#d7dfca';c.lineWidth=1;
  for(let i=0;i<=4;i++){const x=30+(w-45)*i/4;c.beginPath();c.moveTo(x,15);c.lineTo(x,h-25);c.stroke();c.fillStyle='#8d9b7e';c.font='10px system-ui';c.fillText(i+' с',x-5,h-7);}
  c.beginPath();c.moveTo(30,h/2);c.lineTo(w-15,h/2);c.stroke();
  c.strokeStyle='#65804c';c.lineWidth=2.5;c.beginPath();
  for(let i=0;i<=w-45;i++){const t=i/(w-45)*4,x=i+30,y=h/2-Math.sin(2*Math.PI*f*t)*a*36;i?c.lineTo(x,y):c.moveTo(x,y);}c.stroke();
}
amplitude.addEventListener('input',draw);frequency.addEventListener('input',draw);new ResizeObserver(draw).observe(canvas);draw();
