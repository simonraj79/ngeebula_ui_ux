import React from 'react';
import {AbsoluteFill, CanvasImage, Easing, Interactive, interpolate, staticFile, useCurrentFrame} from 'remotion';

export const BG = '#071522';
export const MINT = '#7cebc3';
export const BLUE = '#63a8ff';
export const AMBER = '#ffc574';
export const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const Background: React.FC = () => {
  const f = useCurrentFrame();
  return <AbsoluteFill style={{background: BG, color: '#f5f8fc', overflow: 'hidden'}}>
    <AbsoluteFill style={{background: 'radial-gradient(ellipse at 83% 12%, #153c55 0%, transparent 58%)'}}/>
    <svg width="1920" height="1080" style={{position:'absolute', opacity:0.2}}>
      <defs><pattern id="grid" width="80" height="80" patternUnits="userSpaceOnUse"><path d="M 80 0 L 0 0 0 80" fill="none" stroke="#50819c" strokeWidth="0.7"/></pattern></defs>
      <rect width="1920" height="1080" fill="url(#grid)"/>
      {[0,1,2].map(i=><path key={i} d={`M -80 ${780+i*58} H 600 Q 750 ${780+i*58} 840 ${650+i*58} L 1310 ${160+i*58} Q 1390 ${80+i*58} 1560 ${80+i*58} H 2040`} fill="none" stroke={i===1?MINT:BLUE} strokeWidth="2" strokeDasharray="9 19" strokeDashoffset={-f*0.5}/>) }
    </svg>
  </AbsoluteFill>;
};

export const Brand: React.FC<{section?:string}> = ({section}) => <div style={{position:'absolute',top:42,left:80,right:80,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
  <div style={{display:'flex',gap:13,alignItems:'center',fontSize:29,fontWeight:750,letterSpacing:0.4}}><span style={{width:20,height:20,borderRadius:6,background:MINT,rotate:'45deg'}}/>Ngeebula</div>
  <div style={{fontSize:20,letterSpacing:3,color:'#afc4d7',textTransform:'uppercase'}}>{section || 'RAIL MAINTENANCE PLANNING'}</div>
</div>;

export const Heading: React.FC<{eyebrow:string;title:string;sub?:string}> = ({eyebrow,title,sub}) => {
 const frame=useCurrentFrame();
 return <div style={{position:'absolute',top:106,left:80,right:80}}>
   <div style={{color:MINT,fontSize:23,fontWeight:700,letterSpacing:3,textTransform:'uppercase',marginBottom:10}}>{eyebrow}</div>
   <Interactive.Div name="Scene headline" style={{fontSize:76,fontWeight:750,letterSpacing:-2.4,lineHeight:1.06,opacity:interpolate(frame,[0,16],[0,1],clamp),translate:interpolate(frame,[0,22],['0px 24px','0px 0px'],{...clamp,easing:Easing.out(Easing.cubic)})}}>{title}</Interactive.Div>
   {sub&&<div style={{fontSize:28,color:'#bdd0df',marginTop:13}}>{sub}</div>}
 </div>;
};

export const Screen:React.FC<{src:string; crop?:{x:number;y:number;w:number;h:number}; zoom?:number; children?:React.ReactNode; label?:string; top?:number; height?:number; contain?:boolean; panY?:number}> = ({src,crop={x:330,y:90,w:1230,h:660},zoom=1.015,children,label='ACTUAL APPLICATION · ISOLATED DEMO DATA',top=292,height=650,contain=false,panY})=>{
 const frame=useCurrentFrame();
 const scale=contain?Math.min(1760/crop.w,(height-42)/crop.h):1760/crop.w;
 const offset=contain?(1760-crop.w*scale)/2:0;
 return <div style={{position:'absolute',left:80,top,width:1760,height,border:'1px solid #38617c',borderRadius:22,overflow:'hidden',boxShadow:'0 25px 65px #0008',background:'#081522',opacity:interpolate(frame,[8,25],[0,1],clamp),translate:interpolate(frame,[8,32],['0px 26px','0px 0px'],{...clamp,easing:Easing.out(Easing.cubic)})}}>
   <div style={{position:'absolute',left:0,top:0,width:1760,height:42,background:'#153043',display:'flex',alignItems:'center',gap:7,padding:'0 22px',zIndex:3}}>
     {['#507286','#507286','#7cebc3'].map((c,i)=><span key={i} style={{width:8,height:8,borderRadius:8,background:c}}/>)}<span style={{fontSize:16,color:'#c5d7e5',letterSpacing:1.5,marginLeft:14}}>{label}</span>
   </div>
   <div style={{position:'absolute',top:42,left:0,width:1760,height:height-42,overflow:'hidden'}}>
     <div style={{position:'absolute',left:offset,top:0,width:crop.w*scale,height:height-42,overflow:'hidden'}}>
     <div style={{width:1600*scale,height:900*scale,position:'absolute',left:-crop.x*scale,top:-interpolate(frame,[50,290],[crop.y,panY??crop.y],clamp)*scale,scale:interpolate(frame,[0,360],[1,zoom],clamp),transformOrigin:`${crop.x*scale+880}px ${crop.y*scale+304}px`}}>
       <CanvasImage src={staticFile(`screenshots/${src}`)} style={{width:'100%',height:'100%'}}/>
     </div>
     </div>
     {children}
   </div>
 </div>;
};

export const Callout:React.FC<{text:string;x:number;y:number;w?:number;delay?:number;color?:string;target?:{x:number;y:number;w:number;h:number}}> = ({text,x,y,w=460,delay=40,color=MINT,target})=>{
 const frame=useCurrentFrame();
 return <div style={{opacity:interpolate(frame,[delay,delay+14],[0,1],clamp)}}>
   {target&&<div style={{position:'absolute',left:target.x,top:target.y,width:target.w,height:target.h,border:`3px solid ${color}`,borderRadius:12,boxShadow:`0 0 0 6px ${color}18`,scale:interpolate(frame,[delay,delay+20],[1.06,1],clamp)}}/>}
   {target&&<svg style={{position:'absolute',inset:0,width:'100%',height:'100%',pointerEvents:'none'}}><path d={`M ${x+w/2} ${y+60} L ${x+w/2} ${y+86} L ${target.x+target.w/2} ${target.y}`} stroke={color} strokeWidth="3" fill="none"/><circle cx={target.x+target.w/2} cy={target.y} r="6" fill={color}/></svg>}
   <div style={{position:'absolute',left:x,top:y,width:w,padding:'17px 22px',background:'#092438f5',border:`2px solid ${color}`,borderRadius:12,color:'#fff',fontSize:31,fontWeight:650,lineHeight:1.2,boxShadow:'0 12px 30px #0007',translate:interpolate(frame,[delay,delay+18],['0px 12px','0px 0px'],clamp)}}>{text}</div>
 </div>;
};

export const StepPills:React.FC<{active:number}> = ({active})=><div style={{position:'absolute',left:80,right:80,top:248,display:'flex',gap:14}}>
 {['Select asset','Locate work','Review needs','Generate plan','Approve & track'].map((s,i)=><div key={s} style={{fontSize:20,color:i===active?BG:'#9bb3c5',background:i===active?MINT:'#112a3b',padding:'6px 18px',borderRadius:24,fontWeight:650}}>{i+1} · {s}</div>)}
</div>;

export const Train:React.FC=()=>{
 const f=useCurrentFrame();
 return <svg viewBox="0 0 1000 245" width="1120" height="274" style={{position:'absolute',left:700,top:210,translate:interpolate(f,[0,45],['160px 0px','0px 0px'],{...clamp,easing:Easing.out(Easing.cubic)})}}>
   <path d="M40 35H820Q932 35 965 130V178H40Q15 178 15 148V65Q15 35 40 35Z" fill="#193951" stroke="#68a8c1" strokeWidth="3"/>
   <path d="M823 50Q899 57 930 119H823Z" fill="#78cfdf"/>
   {[0,1,2,3,4,5].map(i=><rect key={i} x={60+i*112} y="61" width="82" height="54" rx="8" fill="#2c6681"/>)}
   <path d="M15 142H963" stroke={MINT} strokeWidth="9"/>
   <rect x="402" y="52" width="86" height="120" rx="6" fill="#203c4e" stroke={AMBER} strokeWidth="4"/>
   <path d="M445 53V172" stroke={AMBER} strokeWidth="2"/>
   {[110,230,690,820].map(x=><circle key={x} cx={x} cy="186" r="22" fill="#071522" stroke="#77a2b6" strokeWidth="7"/>)}
   <path d="M0 216H1000M0 226H1000" stroke="#38647d" strokeWidth="3"/>
   <circle cx="445" cy="108" r={interpolate(f%60,[0,59],[50,94])} fill="none" stroke={AMBER} opacity={interpolate(f%60,[0,59],[0.7,0])} strokeWidth="2"/>
 </svg>;
};
