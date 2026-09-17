import {AbsoluteFill,interpolate,useCurrentFrame} from 'remotion';
import {AMBER,Background,Brand,clamp,Heading,MINT,Screen} from '../visuals';
export const Comparison=()=>{
 const f=useCurrentFrame();
 return <AbsoluteFill><Background/><Brand section="A CONTROLLED DEMONSTRATION"/>
 <Heading eyebrow="Same jobs. Same crew. Same constraints." title="See what joint planning can change."/>
 <div style={{position:'absolute',left:80,right:80,top:264,display:'flex',gap:24,zIndex:4}}>
 {[{label:'Requested slots',n:'1 / 2',note:'Scripted worksheet proxy',color:AMBER},{label:'First available slot',n:'1 / 2',note:'Sequential first-fit',color:AMBER},{label:'Joint planning',n:'2 / 2',note:'Both new repairs fit',color:MINT}].map((item,i)=><div key={item.label} style={{flex:1,padding:'22px 30px',border:`2px solid ${item.color}`,borderRadius:19,background:'#0e2638f7',opacity:interpolate(f,[20+i*28,42+i*28],[0,1],clamp),translate:interpolate(f,[20+i*28,42+i*28],['0px 20px','0px 0px'],clamp)}}>
 <div style={{fontSize:27,fontWeight:600}}>{item.label}</div><div style={{fontSize:88,fontWeight:750,color:item.color,letterSpacing:-3}}>{item.n}</div><div style={{fontSize:21,color:'#b9d0de'}}>{item.note}</div></div>)}
 </div>
 <Screen src="08_compare_approaches.png" top={525} height={390} crop={{x:340,y:542,w:1220,h:355}} contain zoom={1} label="SYNTHETIC SPECIALIST CASE · FIXED INSPECTION RETAINED"/>
 <div style={{position:'absolute',left:80,right:80,top:914,padding:'8px 20px',borderRadius:8,fontSize:21,color:'#d0e0eb',background:'#071522f5',zIndex:5}}>Synthetic example · Not measured human performance or a guaranteed operational result.</div>
 </AbsoluteFill>;
};
