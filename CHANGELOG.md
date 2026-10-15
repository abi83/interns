# Changelog

## [0.3.1](https://github.com/abi83/interns/compare/0.3.0...v0.3.1) (2026-10-15)


### Features

* actor and permission guard in event routing ([#338](https://github.com/abi83/interns/issues/338)) ([#345](https://github.com/abi83/interns/issues/345)) ([d35fa5f](https://github.com/abi83/interns/commit/d35fa5f6b8c2e33ceb6f8d874d70a160f99af6c3))
* automate releases with release-please; floating v0 and next tags ([#331](https://github.com/abi83/interns/issues/331)) ([14fa7e4](https://github.com/abi83/interns/commit/14fa7e4f591f9f796237b1702266575814463817))
* **coder:** allow git mv so the coder can move files ([#288](https://github.com/abi83/interns/issues/288)) ([16adc8e](https://github.com/abi83/interns/commit/16adc8ebe72e9d110b4d49b972de4bee494f61c1))
* **coder:** install deps via make setup; batch tool calls, read-only Bash ([#261](https://github.com/abi83/interns/issues/261)) ([8abc316](https://github.com/abi83/interns/commit/8abc31607b917e4a463d64cd7699f04a633f5424)), closes [#258](https://github.com/abi83/interns/issues/258) [#259](https://github.com/abi83/interns/issues/259)
* **config:** auto_proceed — start the coder automatically after estimation, per size ([#283](https://github.com/abi83/interns/issues/283)) ([9244542](https://github.com/abi83/interns/commit/92445426d3445ab01eb11400a7981f6e692333ed))
* **config:** per-agent allowed_tools and a --tools ceiling for every phase ([#272](https://github.com/abi83/interns/issues/272)) ([3578a0b](https://github.com/abi83/interns/commit/3578a0b0f0f9b546c85a5885361d6773bf6329bb))
* **config:** single source for defaults; installed template ships them commented out ([#279](https://github.com/abi83/interns/issues/279)) ([7584c4d](https://github.com/abi83/interns/commit/7584c4dcdf7b5c62093a42c20707c52e5f1b6977))
* configurable reviewer trigger via agents.reviewer.trigger ([#43](https://github.com/abi83/interns/issues/43)) ([#327](https://github.com/abi83/interns/issues/327)) ([872036c](https://github.com/abi83/interns/commit/872036c3d232f32f639cfbcd4ad85a8e6c67c77e))
* **flag-failure:** explain why the agent stopped and list denied commands; fix denial metrics ([#273](https://github.com/abi83/interns/issues/273)) ([09f10b9](https://github.com/abi83/interns/commit/09f10b9bf8c84007bdb0e4df3ca2fb8fbc6e2bc1))
* guard that workflow steps supply the env their interns command requires ([#358](https://github.com/abi83/interns/issues/358)) ([ea9b46b](https://github.com/abi83/interns/commit/ea9b46b4995ce2d2e6874a146c5e681adff87178))
* **mcp:** per-phase tool exposure and slim list_issues labels ([#267](https://github.com/abi83/interns/issues/267)) ([8f8a296](https://github.com/abi83/interns/commit/8f8a296218877d436142918ca38ef016876961cc))
* Python launcher for claude -p behind a per-phase switch, estimator first ([#347](https://github.com/abi83/interns/issues/347)) ([5fdbb93](https://github.com/abi83/interns/commit/5fdbb93506ca900aea3bbb7017810dcb8d45ac6f))
* remove claude-code-action plumbing ([#343](https://github.com/abi83/interns/issues/343)) ([#354](https://github.com/abi83/interns/issues/354)) ([fec45b2](https://github.com/abi83/interns/commit/fec45b2ec0f345c08528f58950b0fd77d570a933))
* review on check_suite completion instead of every push ([#238](https://github.com/abi83/interns/issues/238)) ([#329](https://github.com/abi83/interns/issues/329)) ([dad391a](https://github.com/abi83/interns/commit/dad391aae79d2cbecb39d8bcc7e774c16b9d1ea2))
* run the coder (initial + fix round) through the Python launcher ([#350](https://github.com/abi83/interns/issues/350)) ([3eb450a](https://github.com/abi83/interns/commit/3eb450abfd633ac332ab6abc3cfa76fb3a8aec0a))
* run the refiner through the Python launcher ([#340](https://github.com/abi83/interns/issues/340)) ([#348](https://github.com/abi83/interns/issues/348)) ([9b7f1b8](https://github.com/abi83/interns/commit/9b7f1b89740292203f25629cbe4f177490aeb8e9))
* run the reviewer through the Python launcher ([#349](https://github.com/abi83/interns/issues/349)) ([229fabd](https://github.com/abi83/interns/commit/229fabdd10f52f0620e1dc04a8c303ec815e9018))
* **workflows:** allowlist built-in tools for refiner and estimator via --tools ([#265](https://github.com/abi83/interns/issues/265)) ([db88bfc](https://github.com/abi83/interns/commit/db88bfc5763d82f97890bfed246c5ba337373f8c))


### Bug Fixes

* **checks:** red-checks comment points to Makefile targets, not 'coder runs tests' ([#264](https://github.com/abi83/interns/issues/264)) ([7086486](https://github.com/abi83/interns/commit/7086486c1f9241ac42e4de8c554e1ebd0f91ce96))
* **coder:** allowlist the triage App so auto_proceed can start the coder ([#282](https://github.com/abi83/interns/issues/282)) ([#284](https://github.com/abi83/interns/issues/284)) ([8fb2c2b](https://github.com/abi83/interns/commit/8fb2c2bfcd02188fb5a0eab419fcb587b2e120fb))
* **coder:** wiki at sibling dir with --add-dir; draft PR on failure; reviewer skips drafts ([#277](https://github.com/abi83/interns/issues/277)) ([2bd5235](https://github.com/abi83/interns/commit/2bd523554671efaef32911a8f0f603d009ea1268))
* do not fail a successful agent run for exceeding max turns ([#285](https://github.com/abi83/interns/issues/285)) ([#377](https://github.com/abi83/interns/issues/377)) ([30e891f](https://github.com/abi83/interns/commit/30e891f110ca5a282e8d37ed793f024ad67ae7f8))
* fail fast on missing config defaults and env ([#290](https://github.com/abi83/interns/issues/290), [#292](https://github.com/abi83/interns/issues/292)) ([#300](https://github.com/abi83/interns/issues/300)) ([3a1f250](https://github.com/abi83/interns/commit/3a1f250fbc2fded47c7fc0752cc307a7a0dec69c))
* **fetch-issue:** hide pipeline comments from view_issue ([#275](https://github.com/abi83/interns/issues/275)) ([dca2099](https://github.com/abi83/interns/commit/dca2099b756992914c942ee894d071a32627d24c))
* installer branch-protection check covers the interns Apps ([#366](https://github.com/abi83/interns/issues/366)) ([#374](https://github.com/abi83/interns/issues/374)) ([099c278](https://github.com/abi83/interns/commit/099c278db1085a678d68548cc503201b0cc488cd))
* **installer:** route dashboard through install PR, surface errors on stdout ([#242](https://github.com/abi83/interns/issues/242)) ([acad7d8](https://github.com/abi83/interns/commit/acad7d834249828ad0ee1dad555b9b4f961475d1))
* make all label edits strict ([#368](https://github.com/abi83/interns/issues/368)) ([3aa2dd7](https://github.com/abi83/interns/commit/3aa2dd71fdda4666babcb3c6551b1e23472f835c))
* **metrics:** upload artifact and show cost on failed runs ([#244](https://github.com/abi83/interns/issues/244)) ([a243c01](https://github.com/abi83/interns/commit/a243c014f89f42073d7f0b85b3e0a3587723a3c4))
* remove dead MAX_AUTOMATIC_REVIEWS_PER_PR env var ([#312](https://github.com/abi83/interns/issues/312)) ([#315](https://github.com/abi83/interns/issues/315)) ([256cf50](https://github.com/abi83/interns/commit/256cf50229c30f0e64e29304fe7fe6826a9e3bd0))
* restrict refiner label writes to type:* via set_issue_type ([#307](https://github.com/abi83/interns/issues/307)) ([#317](https://github.com/abi83/interns/issues/317)) ([dc2df8f](https://github.com/abi83/interns/commit/dc2df8fa6f63fe26aff303fc6a447d76962de65f))
* reviewer dispatch gate and check-name script injection ([#306](https://github.com/abi83/interns/issues/306), [#308](https://github.com/abi83/interns/issues/308)) ([#316](https://github.com/abi83/interns/issues/316)) ([31984e0](https://github.com/abi83/interns/commit/31984e0219eb090a40d6bab302d94092c6ef4278))
* **reviewer:** clear error when view_issue number is a PR ([#260](https://github.com/abi83/interns/issues/260)) ([7701546](https://github.com/abi83/interns/commit/77015460fabf2386a3c7852eb6dec4b1732fab25))
* **reviewer:** red checks escalate only the PR ([#289](https://github.com/abi83/interns/issues/289)) ([#298](https://github.com/abi83/interns/issues/298)) ([15f3351](https://github.com/abi83/interns/commit/15f335114dc0e8e13f5fe1ea08fc166755f8a8bd))
* route reviewer PR/CI reads through MCP tools ([#361](https://github.com/abi83/interns/issues/361)) ([#375](https://github.com/abi83/interns/issues/375)) ([c622d0d](https://github.com/abi83/interns/commit/c622d0d79ed2c15b7b9fef23d6b7adc79a28c9c4))
* run-summary requires REVIEWER_BOT only for the review phase ([#352](https://github.com/abi83/interns/issues/352)) ([ae07992](https://github.com/abi83/interns/commit/ae07992428a58137ac7b53e71880b5bdfdd10e7d))
* trigger the reviewer on workflow_run instead of check_suite ([#333](https://github.com/abi83/interns/issues/333)) ([#334](https://github.com/abi83/interns/issues/334)) ([195402b](https://github.com/abi83/interns/commit/195402b20d20597d7d90987d0352c0629f3e7a6f))
* use the default GITHUB_TOKEN for release-please ([#332](https://github.com/abi83/interns/issues/332)) ([6e009e3](https://github.com/abi83/interns/commit/6e009e3b3e12096f6daf9ae880382f71dc88ca30))
