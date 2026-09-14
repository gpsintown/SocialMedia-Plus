# Third-party notices

The original application code and newly written portable instructions are under
the root MIT license. Included third-party material retains its own license and
copyright notices. No private upstream repository checkout is distributed.

| Material | Source snapshot used | Included notice |
| --- | --- | --- |
| Humanizer | [blader/humanizer](https://github.com/blader/humanizer), commit `9862685f575c65a8247f90369951df1b3416e3d6` | `.agents/skills/humanizer/LICENSE` (MIT) |
| Strategy/social skills and reference material | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills), commit `5b2c0007766c6a1cf1d53fd8fc73e979e0821022` | Skill-local LICENSE files (MIT) |
| Council review reference | [ngmeyer/skills](https://github.com/ngmeyer/skills), commit `701dfb8bd2ffe22f6aeccc310b6eea3b20462bf1` | `.agents/skills/council-review/LICENSE` (MIT) |
| LinkedIn writing reference | [sarveshtalele/linkedin-content-skill](https://github.com/sarveshtalele/linkedin-content-skill), commit `7a1f7478dfd4ea56c1f43069ba4ad8abee8bf033` | `.agents/skills/linkedin-content/LICENSE` (MIT) |
| React, React DOM and Scheduler in the compiled UI | Versions resolved by `ui/package-lock.json` | `licenses/` (MIT) |

The same skill notices accompany the `.claude/skills/` copies. Application
wrappers adapt the skills to the selected desktop model and local records;
upstream scripts, hooks and installers are not implicitly authorized.

An earlier private installation inspected
[aiwithremy/claude-skills-llm-council](https://github.com/aiwithremy/claude-skills-llm-council).
Its inspected snapshot had no license grant on file. None of that snapshot or its
upstream skill text is included in this release. The portable `llm-council`
entry point contains newly written, generic independent review instructions.

Postiz application, deployment, agent CLI and upstream skill text are excluded.
The retained `postiz` skill name is a newly written compatibility notice for
users encountering old command references; it provides no Postiz integration.
No Postiz AGPL code is bundled or required by this runtime.

Build tools and their dependencies are installed by package managers, not
vendored here. Their licenses are available in the installed packages. Host
applications, subscriptions, browser integrations and connected services remain
separate products governed by their own terms.
