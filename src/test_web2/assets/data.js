'use strict';
const owners=['Ethan Zins','Alex Morgan','Jamie Lee','Sam Kim'];
const statuses=['To do','In progress','In review','Done'];
const seed=[
['Map the onboarding journey','Outline the first five minutes for a new visitor.','To do','Research','Medium',1,'2026-10-29'],['Build the pricing page','Translate the approved layout into a responsive page.','To do','Development','High',0,'2026-10-30'],['Write empty-state copy','Give every quiet corner a helpful next step.','To do','Design','Low',2,'2026-11-03'],
['Design the landing page','Explore a stronger opening and a clearer hierarchy.','In progress','Design','High',3,'2026-10-28'],['Set up the component library','Create reusable buttons, fields, and navigation.','In progress','Development','Medium',0,'2026-10-30'],['Test mobile navigation','Check small screens, touch targets, and keyboard use.','In progress','Testing','Medium',1,'2026-11-02'],
['Review the homepage copy','One final pass for clarity, tone, and consistency.','In review','Design','Medium',2,'2026-10-27'],['Check form accessibility','Review labels, focus order, and error messages.','In review','Testing','High',1,'2026-10-29'],
['Define project milestones','Turn the launch plan into manageable checkpoints.','Done','Research','Medium',0,'2026-10-21'],['Finalize the color palette','Document the core colors and accessible pairings.','Done','Design','Low',3,'2026-10-22'],['Set up the repository','Add the project structure and contribution notes.','Done','Development','Medium',0,'2026-10-23'],['Collect reference material','Gather examples and agree on a visual direction.','Done','Research','Low',2,'2026-10-23']
].map((a,i)=>({id:i+1,title:a[0],description:a[1],status:a[2],category:a[3],priority:a[4],owner:owners[a[5]],date:a[6],archived:false}));
