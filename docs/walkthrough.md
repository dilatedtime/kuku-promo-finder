# Three-minute walkthrough

Private assignment recording. Use synthetic content for any public demo. Aim for about 130-140 words per minute; rehearse once.

**0:00-0:25 | Show the app and problem**

I chose Problem 1, finding promos. An editor has to search every episode for a strong opening and a cut that leaves something unresolved. My tool turns a timed screenplay into a review queue with source-backed cut points. It does not edit video or claim to predict a successful ad.

**0:25-0:55 | Run a new input**

Here I am running a synthetic episode, so you can see the pipeline accept new input. The offline option checks the plumbing. The local Qwen model supplies editorial judgments. All model access sits behind one provider interface, so I can replace the endpoint and model through configuration. Invalid or missing timestamps fail clearly.

**0:55-1:25 | Open the real full-pack report**

The full run searched all fifty episodes and three thousand seven hundred and twenty-seven timed blocks. It judged one hundred and eighty-one candidates, including thirty-one proposed stitches. Code checks the exact boundaries, total runtime, segment order and quoted evidence. The final queue has 21 clips after the review gate. Here are the segments and the individual scores.

**1:25-2:05 | Show a real failure and correction**

The model ranks Episode 12 first, but I would review Episode 44 first for a posting test. Its rejection line lands within two seconds. Episode 12 starts with a generic question. This disagreement is visible in the failure analysis. A model also called a threatened husband a brother, then a sister. A word check was insufficient; a source-review note produced a safer explanation. I kept all the original responses. Critic review is now a gate, so unchecked or model-resolved clips cannot move into the final ranking.

**2:05-2:35 | Show evidence and cost**

All mechanical checks pass, and seventy-nine tests pass. A fresh sampling stress run shares nine of the top ten picks. That measures stability, not correctness. The main path used about two hundred and seventy-two thousand input tokens and twenty-two thousand output tokens locally. API spend was zero. A stronger-model estimate is roughly eighty-one cents per show, with different tokenization and reasoning costs still uncertain.

**2:35-3:00 | Show the review sheet and finish**

The human label columns are blank. I would label all 21 clips, inspect the top ten against footage, and approve boundaries before posting. The metric script computes precision-style results after labelling. Text alone cannot establish acting, sound, visual impact or conversion. The tool reduces the search; the editor makes the posting decision.
