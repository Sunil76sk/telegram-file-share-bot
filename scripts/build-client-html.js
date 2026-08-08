import fs from "fs";
import path from "path";

const clientDir = path.resolve("dist/client");
const assetsDir = path.resolve("dist/client/assets");

if (fs.existsSync(assetsDir)) {
  const files = fs.readdirSync(assetsDir);
  const jsFile =
    files.find((f) => f.startsWith("index-s3-") && f.endsWith(".js")) ||
    files.find((f) => f.startsWith("index-") && f.endsWith(".js"));
  const cssFile = files.find((f) => f.endsWith(".css"));

  const html = `<!DOCTYPE html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MovieMagic Bot - Admin Dashboard</title>
    ${cssFile ? `<link rel="stylesheet" href="/assets/${cssFile}">` : ""}
  </head>
  <body class="bg-background text-foreground">
    <div id="root"></div>
    ${jsFile ? `<script type="module" src="/assets/${jsFile}"></script>` : ""}
  </body>
</html>`;

  fs.writeFileSync(path.join(clientDir, "index.html"), html);
  fs.writeFileSync(path.join(clientDir, "_redirects"), "/* /index.html 200\n");
  console.log("✅ Generated dist/client/index.html with JS:", jsFile, "and CSS:", cssFile);
}
