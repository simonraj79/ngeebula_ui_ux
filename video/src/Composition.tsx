import {AbsoluteFill,Sequence,staticFile,useCurrentFrame,interpolate} from 'remotion';
import {Audio} from '@remotion/media';
import {TransitionSeries,linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {wipe} from '@remotion/transitions/wipe';
import {Captions} from './Captions';
import {clamp} from './visuals';
import {Hook} from './scenes/01-Hook';
import {Context} from './scenes/02-Context';
import {Cockpit} from './scenes/03-Cockpit';
import {Assets} from './scenes/04-Assets';
import {Location} from './scenes/05-Location';
import {Review} from './scenes/06-Review';
import {Plan} from './scenes/07-Plan';
import {Approval} from './scenes/08-Approval';
import {Comparison} from './scenes/09-Comparison';
import {Close} from './scenes/10-Close';
const starts=[0,8,19,28,39,50,61,75,87,101];
export const StakeholderVideo=()=>{
 const frame=useCurrentFrame();
 return <AbsoluteFill style={{fontFamily:'Segoe UI, Arial, sans-serif',background:'#071522',color:'#f6f9fc'}}>
 <TransitionSeries>
<TransitionSeries.Sequence durationInFrames={252} name="01 · Hook"><Hook/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={342} name="02 · Context"><Context/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={wipe({direction:"from-right"})} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={282} name="03 · Cockpit"><Cockpit/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={342} name="04 · Assets"><Assets/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={342} name="05 · Location"><Location/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={342} name="06 · Review"><Review/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={wipe({direction:"from-right"})} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={432} name="07 · Plan"><Plan/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={372} name="08 · Approval"><Approval/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={wipe({direction:"from-right"})} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={432} name="09 · Comparison"><Comparison/></TransitionSeries.Sequence>
<TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:12})}/>
<TransitionSeries.Sequence durationInFrames={390} name="10 · Close"><Close/></TransitionSeries.Sequence>
</TransitionSeries>
 {starts.map((s,i)=><Sequence key={s} from={Math.round((s+.55)*30)} layout="none" name={`Narration ${i+1}`}><Audio src={staticFile(`audio/voice-${String(i+1).padStart(2,'0')}.mp3`)}/></Sequence>)}
 <Audio src={staticFile('audio/original-score.mp3')} volume={0.65}/>
 <Captions/>
 <div style={{position:'absolute',bottom:0,left:0,height:4,width:interpolate(frame,[0,3420],[0,1920],clamp),background:'#7cebc3',opacity:0.6}}/>
 <AbsoluteFill style={{background:'#071522',opacity:interpolate(frame,[0,10,3405,3419],[1,0,0,1],clamp),pointerEvents:'none'}}/>
 </AbsoluteFill>;
};
