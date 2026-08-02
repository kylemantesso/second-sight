# Arm AI Optimization Challenge 2026

This project is intended for the **Physical AI** track of the Arm AI
Optimization Challenge 2026. This page records the challenge brief and
submission expectations supplied for the project, so they remain available
alongside the implementation documentation.

## Challenge overview

The challenge invites developers to build projects that show how AI can be
optimized for Arm-powered platforms across three tracks:

| Track | Focus |
| --- | --- |
| Physical AI | Real-world systems including robotics, embedded devices, sensors, simulation, autonomy, and edge environments. |
| Cloud AI | Scalable infrastructure including Arm64 cloud, inference performance, frameworks, agents, and production-ready developer workflows. |
| Mobile AI | On-device constraints including performance, privacy, latency, battery efficiency, and local AI experiences on Arm-powered phones, tablets, and laptops. |

Across every track, submissions should demonstrate clear optimization work and,
where possible, measurable improvements.

## Optimizations judges will look for

- **Model size:** reduce disk or memory footprint.
- **Model quality:** improve fine-tuning or output quality for a given model
  size.
- **Model speed:** improve tokens per second, time to first token, or other
  relevant latency metrics.
- **Inference-server speed:** improve throughput, latency, tokens per second,
  or time to first token.
- **Developer experience:** improve tools, workflows, setup, documentation, or
  usability.
- **Arm-specific optimization:** improve an existing framework, library,
  model, or application running on Arm.

Arm Performix can be used to produce exact Arm-based performance benchmarks
and clearly present the results.

## Submission requirements

Submissions must:

- Build with the required developer tools and meet the project requirements
  for the selected track.
- Provide a URL to a public code repository for judging and testing. The
  repository must contain all source code, assets, and instructions needed for
  the project to function.
- Be open source, with a detectable and visible MIT or Apache 2.0 license.
- Include a text description covering:
  - **Project overview:** purpose, what makes the project interesting, and why
    it should win.
  - **Functionality/output:** what the project does and its final output, such
    as an optimized model, migration example, or other deliverable.
  - **Setup instructions:** step-by-step build, run, and validation steps on
    an Arm-powered device or Arm64 environment when applicable.

For Track 1 (Physical AI) and Track 2 (Cloud AI), each submission must include
a copy of the source code, either attached directly or linked to an open-source
repository such as GitHub. Track 3 (Mobile AI) submissions must include the
proof artifacts required by that track.

### Optional demonstration video

If submitted, the video must:

- be no longer than three minutes; judges are not required to watch beyond
  that limit;
- show the project functioning on its target device;
- be publicly visible on YouTube, Vimeo, or Youku, with its link included in
  the submission form; and
- not contain third-party trademarks, copyrighted music, or other material
  without permission.

## Prizes

The challenge offers **$8,000 in prizes**:

| Prize | Award | Winners |
| --- | --- | --- |
| Overall Winner | $3,000 cash and a feature in the Arm Community Blog | 1 |
| Overall Runner Up | $2,000 cash and a feature in the Arm Community Blog | 1 |
| Best in Category: Physical AI | $1,000 cash and a feature in the Arm Community Blog | 1 |
| Best in Category: Cloud AI | $1,000 cash and a feature in the Arm Community Blog | 1 |
| Best in Category: Mobile AI | $1,000 cash and a feature in the Arm Community Blog | 1 |

## Judges

- Avin Zarlez — Arm Staff Software Engineer, Developer Evangelist
- Michael Hall — Arm Principal Software Engineer, Developer Evangelist
- Gabriel Peterson — Arm Senior ML Engineer, Developer Evangelist
- Rani Chowdary Mandepudi — Software Engineer, Strategy & Ecosystems, Arm
- Disha Patil — Senior Developer Relations Engineer, Arm
- Sicong Li — Staff Software Engineer

## Judging criteria

| Criterion | Points | What judges assess |
| --- | ---: | --- |
| Technological implementation | 40 | Quality software development, effective use of Arm-powered platforms, efficiency-minded design, and a sound technical approach. |
| User experience / developer experience | 15 | Whether the project is clear to use, run, and validate; documentation quality; and potential for reuse or extension. |
| Potential impact | 20 | Usefulness to the developer community and reusable artifacts such as optimized models, migration templates, prompt assets, or learning-ready content. |
| WOW factor | 25 | Creativity, compelling presentation, usefulness, clarity, and ability to capture attention quickly. |

## Resources and support

- [Arm Developer Program](https://developer.arm.com/) — technical
  documentation, development tools, and community support.
- [Arm Learning Paths](https://learn.arm.com/) — guided learning on Arm
  architecture and AI topics.
- [Arm Developer Ecosystem GitHub](https://github.com/ArmDeveloperEcosystem) —
  open-source projects and code examples.

The challenge also provides workshops and office hours through the Arm
Developer Program Discord, where developers can contact Arm engineers and
evangelists for support.

## Relevance to Second Sight

Second Sight is a Physical AI submission: it monitors an autonomous-driving
simulation with a small anomaly detector on an isolated Arm-capable workload.
The intended evidence for this track is measured Arm Linux inference and
end-to-end detection latency, model footprint, CPU overhead, and Arm Performix
results. See the [project build brief](brief.md) for the implementation plan
and [baseline report](../reports/baseline.md) for the current development-only
results.
