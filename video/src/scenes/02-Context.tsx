import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {AMBER, Background, Brand, clamp, Heading, MINT} from '../visuals';
export const Context=()=>{
 const f=useCurrentFrame();
 return <AbsoluteFill><Background/><Brand section="SINGAPORE CONTEXT"/><Heading eyebrow="Why this matters" title="Many worksites. A narrow window."/>
 <div style={{position:'absolute',left:80,right:80,top:310,display:'flex',gap:28}}>
  <div style={{width:730,height:570,border:'1px solid #376079',borderRadius:24,background:'#102b3c',padding:42}}>
   <div style={{color:AMBER,fontSize:24,letterSpacing:2}}>CNA · 1 APRIL 2025</div>
   <div style={{fontSize:162,lineHeight:1.2,fontWeight:750,letterSpacing:-8,marginTop:28}}>3<span style={{fontSize:75,letterSpacing:-2}}> hours</span></div>
   <div style={{fontSize:34,lineHeight:1.45,color:'#d1e1ec'}}>One observed rail-replacement shift:<br/><b>1:30 am to 4:30 am</b></div>
   <div style={{fontSize:22,color:'#a5c0d2',lineHeight:1.4,marginTop:38}}>Reported example, not a universal<br/>maintenance timetable.</div>
  </div>
  <div style={{flex:1,height:570,border:'1px solid #376079',borderRadius:24,background:'#102b3c',padding:42,opacity:interpolate(f,[65,95],[0,1],clamp)}}>
   <div style={{color:MINT,fontSize:24,letterSpacing:2}}>THE STRAITS TIMES · 1 APRIL 2025</div>
   <div style={{fontSize:120,fontWeight:750,marginTop:35,letterSpacing:-5}}>~1,000 <span style={{fontSize:42,letterSpacing:-1,fontWeight:500}}>workers</span></div>
   <div style={{fontSize:120,fontWeight:750,letterSpacing:-5}}>150 <span style={{fontSize:42,letterSpacing:-1,fontWeight:500}}>worksites</span></div>
   <div style={{fontSize:28,color:'#bfd5e3',marginTop:22,lineHeight:1.5}}>Nightly maintenance scale reported by SMRT.<br/>Coordination matters before work begins.</div>
  </div>
 </div><div style={{position:'absolute',left:82,top:905,fontSize:20,color:'#a5bed0'}}>Sources paraphrased. Full article links and scope notes accompany this video.</div>
 </AbsoluteFill>;
};
