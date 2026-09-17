import {AbsoluteFill} from 'remotion';
import {Background,Brand,Callout,Heading,Screen,StepPills} from './visuals';
type Props={eyebrow:string;title:string;src:string;active:number|null;cropY:number;top:string;bottom:string};
export const ProductShot=({eyebrow,title,src,active,cropY,top,bottom}:Props)=><AbsoluteFill>
<Background/><Brand section="FROM MAINTENANCE NEED TO REVIEWABLE PLAN"/>
<Heading eyebrow={eyebrow} title={title}/>{active!==null&&<StepPills active={active}/>}
<Screen src={src} crop={{x:330,y:cropY,w:1230,h:660}}>
<Callout text={top} x={870} y={30} w={780} delay={48}/>
<Callout text={bottom} x={570} y={472} w={1080} delay={140}/>
</Screen></AbsoluteFill>;
