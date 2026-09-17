import {AbsoluteFill, Interactive, interpolate, useCurrentFrame} from 'remotion';
import {AMBER, Background, Brand, clamp, MINT, Train} from '../visuals';
export const Hook=()=>{
 const f=useCurrentFrame();
 return <AbsoluteFill><Background/><Brand section="THE PLANNING CHALLENGE"/>
 <div style={{position:'absolute',left:80,top:150,width:780}}>
  <div style={{fontSize:25,color:MINT,letterSpacing:3,fontWeight:700}}>THE NIGHT IS SHORT.</div>
  <Interactive.Div name="Hook title" style={{fontSize:116,fontWeight:750,lineHeight:1.04,letterSpacing:-4,marginTop:22,opacity:interpolate(f,[0,22],[0,1],clamp)}}>The repair<br/>cannot wait.</Interactive.Div>
  <div style={{fontSize:35,color:'#c0d4e3',lineHeight:1.4,marginTop:28,width:680}}>How does new work fit around an already approved plan?</div>
 </div><Train/>
 <div style={{position:'absolute',left:80,right:80,top:638,padding:'25px 30px 35px',background:'#0e2638',border:'1px solid #345368',borderRadius:22}}>
  <div style={{fontSize:23,color:'#9db6ca',marginBottom:20}}>ILLUSTRATIVE OVERNIGHT PLAN</div>
  <div style={{height:84,position:'relative',background:'#071722',borderRadius:12,display:'flex',gap:12,padding:12}}>
   {['Preventive inspection','Scheduled servicing','Fixed commitment'].map((t,i)=><div key={t} style={{marginLeft:i===1?65:0,width:i===2?340:380,background:'#244f64',border:'1px solid #5d8a9f',borderRadius:8,padding:15,fontSize:24,color:'#d9e8f2'}}>▣ {t}</div>)}
   <div style={{position:'absolute',right:58,top:-166,width:410,padding:24,borderRadius:14,background:AMBER,color:'#172532',boxShadow:'0 15px 50px #0008',fontSize:30,fontWeight:750,translate:interpolate(f,[74,108],['180px 0px','0px 0px'],clamp),opacity:interpolate(f,[74,96],[0,1],clamp)}}>+ Corrective repair<br/><span style={{fontSize:22,fontWeight:500}}>Same window. New deadline.</span><div style={{position:'absolute',bottom:-12,left:184,width:24,height:24,rotate:'45deg',background:AMBER}}/></div>
  </div>
 </div></AbsoluteFill>;
};
