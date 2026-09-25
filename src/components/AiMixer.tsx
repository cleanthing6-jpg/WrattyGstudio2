23:53:09.127 Running build in Washington, D.C., USA (East) – iad1
23:53:09.129 Build machine configuration: 2 cores, 8 GB
23:53:09.359 Cloning github.com/cleanthing6-jpg/WrattyGstudio2 (Branch: main, Commit: 5d6ef2d)
23:53:10.199 Cloning completed: 836.000ms
23:53:11.401 Restored build cache from previous deployment (4oiTbmmRMysVSs1qGciwxFF5KwUJ)
23:53:12.188 Running "vercel build"
23:53:12.223 Vercel CLI 59.25.4
23:53:12.553 Running "install" command: `npm install`...
23:53:14.981 
23:53:14.983 up to date, audited 431 packages in 2s
23:53:14.984 
23:53:14.984 158 packages are looking for funding
23:53:14.984   run `npm fund` for details
23:53:15.001 
23:53:15.001 4 high severity vulnerabilities
23:53:15.002 
23:53:15.002 To address all issues (including breaking changes), run:
23:53:15.002   npm audit fix --force
23:53:15.002 
23:53:15.003 Run `npm audit` for details.
23:53:15.003 npm warn install-scripts 2 packages have install scripts not yet covered by allowScripts:
23:53:15.004 npm warn install-scripts   msgpackr-extract@3.0.4 (install: node-gyp rebuild)
23:53:15.004 npm warn install-scripts   unrs-resolver@1.12.2 (postinstall: node postinstall.js)
23:53:15.004 npm warn install-scripts
23:53:15.005 npm warn install-scripts Run `npm install-scripts ls` to review, or `npm install-scripts approve <pkg>` to allow.
23:53:15.062 Detected Next.js version: 16.3.4
23:53:15.064 Running "next build"
23:53:15.787 ▲ Next.js 16.3.4 (Turbopack)
23:53:16.098   Applying modifyConfig from Vercel
23:53:16.101 ✓ Running next.config.ts took 313ms
23:53:16.127 
23:53:16.196   Creating an optimized production build ...
23:53:25.741 
23:53:25.743 > Build error occurred
23:53:25.746 Error: Turbopack build failed with 1 error:
23:53:25.746 ./src/components/AiMixer.tsx:11:9
23:53:25.746 Error: Expected ',', got '.'
23:53:25.747    9 |     preview: true,
23:53:25.747   10 |   }),
23:53:25.747 > 11 |   if (fr.ok && fj.url) url = fj.url;
23:53:25.747      |         ^
23:53:25.748   12 |   else console.warn("[vocal-fx]", fj.error || fr.status);
23:53:25.748   13 | } catch (e) {
23:53:25.748   14 |   console.warn("[vocal-fx] skipped:", e);
23:53:25.748 
23:53:25.748 Parsing ecmascript source code failed
23:53:25.748 
23:53:25.749 Import traces:
23:53:25.749   Client Component Browser:
23:53:25.749     ./src/components/AiMixer.tsx [Client Component Browser]
23:53:25.749     ./src/app/studio/page.tsx [Client Component Browser]
23:53:25.749     ./src/app/studio/page.tsx [Server Component]
23:53:25.749 
23:53:25.750   Client Component SSR:
23:53:25.750     ./src/components/AiMixer.tsx [Client Component SSR]
23:53:25.750     ./src/app/studio/page.tsx [Client Component SSR]
23:53:25.750     ./src/app/studio/page.tsx [Server Component]
23:53:25.750 
23:53:25.750 
23:53:25.750     at <unknown> (./src/components/AiMixer.tsx:11:9)
23:53:25.838 Error: Command "next build" exited with 1
