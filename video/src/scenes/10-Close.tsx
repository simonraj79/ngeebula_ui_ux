import {AbsoluteFill,interpolate,useCurrentFrame} from 'remotion';
import {Background,Brand,clamp,MINT,BLUE} from '../visuals';
export const Close=()=>{
 const f=useCurrentFrame();
 return <AbsoluteFill><Background/><Brand section="STAKEHOLDER DEMONSTRATION"/>
 <div style={{position:'absolute',top:154,left:80,right:80}}>
  <div style={{fontSize:25,color:MINT,letterSpacing:3,fontWeight:700}}>OPTIONAL AI. HUMAN ACCOUNTABILITY.</div>
  <div style={{fontSize:105,fontWeight:750,lineHeight:1.05,letterSpacing:-4,marginTop:25}}>Clear constraints.<br/>Reviewable plans.<br/><span style={{color:MINT}}>Human approval.</span></div>
  <div style={{fontSize:30,color:'#bed1df',marginTop:32,width:1060,lineHeight:1.4}}>Gemini can assist free-text assessment after catalog validation.<br/>Core rules and scheduling work without AI.</div>
 </div>
 <div style={{position:'absolute',right:80,top:190,width:410,padding:32,border:'1px solid #3b637c',borderRadius:22,background:'#102c3e',fontSize:27,lineHeight:1.8,opacity:interpolate(f,[30,65],[0,1],clamp)}}>
  {['Select the asset','Locate the work','Review requirements','Generate a proposal','Approve and track'].map((t,i)=><div key={t}><span style={{color:BLUE,marginRight:13}}>0{i+1}</span>{t}</div>)}
 </div>
 <div style={{position:'absolute',left:80,right:80,top:755,borderTop:'1px solid #365b72',paddingTop:26,opacity:interpolate(f,[115,140],[0,1],clamp)}}>
  <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><span style={{fontSize:31,color:'#c1d6e5'}}>Explore the working demo</span><span style={{fontSize:42,color:MINT,fontWeight:650}}>ngeebula-ui-ux.onrender.com ↗</span></div>
  <div style={{fontSize:21,color:'#9db7ca',marginTop:20,lineHeight:1.45}}>Planning prototype · Dummy roster and synthetic demonstrations · No live operational feed<br/>Not incident response or safety authorization. News context does not imply operator endorsement.</div>
 </div></AbsoluteFill>;
};
