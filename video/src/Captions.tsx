import type {Caption} from '@remotion/captions';
import {useCurrentFrame,useVideoConfig} from 'remotion';
import captionsData from '../public/captions.json';

export const Captions=()=>{
 const frame=useCurrentFrame();const {fps}=useVideoConfig();
 const now=frame/fps*1000;
 const active=(captionsData as Caption[]).find(c=>now>=c.startMs&&now<c.endMs);
 if(!active)return null;
 return <div style={{position:'absolute',left:150,right:150,bottom:32,display:'flex',justifyContent:'center',zIndex:10}}>
   <div style={{background:'#030b12ee',border:'1px solid #335066',borderRadius:13,padding:'13px 30px',fontFamily:'Segoe UI, Arial, sans-serif',fontSize:35,lineHeight:1.3,textAlign:'center',color:'#ffffff',maxWidth:1580,boxShadow:'0 6px 30px #0005'}}>{active.text}</div>
 </div>;
};
