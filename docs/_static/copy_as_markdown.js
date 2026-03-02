/**
 * Adds a "Copy as Markdown" button to each documentation page.
 *
 * Fetches the pre-built .md file for the current page (generated at build
 * time by the sphinx-llm extension) and copies its content to the clipboard.
 * If JS is disabled or the .md file is missing, the button simply won't
 * appear or will show "Not available" — no existing page content is affected.
 *
 * Security notes:
 * - No innerHTML: all DOM nodes are created via createElement/createElementNS
 * - fetch() uses a same-origin relative URL only
 * - All text updates use textContent (not innerHTML) to prevent XSS
 */
document.addEventListener("DOMContentLoaded", function () {
  var contentArea = document.querySelector("[role='main']");
  if (!contentArea) return;

  // sphinx-llm generates a .md companion for each .html page
  // e.g. /intro/tutorial.html -> /intro/tutorial.html.md
  var mdUrl = window.location.pathname;
  if (mdUrl.endsWith("/")) mdUrl += "index.html";
  mdUrl += ".md";

  // Build button with DOM APIs only (no innerHTML for security)
  var btn = document.createElement("button");
  btn.className = "copy-as-markdown-btn";
  btn.setAttribute("title", "Copy page as Markdown");

  // Clipboard SVG icon
  var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2");
  var rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.setAttribute("x", "8");
  rect.setAttribute("y", "2");
  rect.setAttribute("width", "8");
  rect.setAttribute("height", "4");
  rect.setAttribute("rx", "1");
  rect.setAttribute("ry", "1");
  svg.appendChild(path);
  svg.appendChild(rect);

  var label = document.createElement("span");
  label.className = "copy-as-markdown-label";
  label.textContent = "Copy as Markdown";

  btn.appendChild(svg);
  btn.appendChild(label);
  contentArea.insertBefore(btn, contentArea.firstChild);

  // Fetch the pre-built markdown and copy to clipboard
  btn.addEventListener("click", function () {
    fetch(mdUrl)
      .then(function (response) {
        if (!response.ok) throw new Error("Not found");
        return response.text();
      })
      .then(function (markdown) {
        return navigator.clipboard.writeText(markdown);
      })
      .then(function () {
        label.textContent = "Copied!";
        btn.classList.add("copied");
        setTimeout(function () {
          label.textContent = "Copy as Markdown";
          btn.classList.remove("copied");
        }, 2000);
      })
      .catch(function () {
        label.textContent = "Not available";
        setTimeout(function () {
          label.textContent = "Copy as Markdown";
        }, 2000);
      });
  });
});
