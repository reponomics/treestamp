import { treeGuides, appendTreeGuides } from "./tree-view.js";

// Keep the sample's content in HTML and use the same continuous branches as
// the editor, picker, and note-placement tree. This is display-only content.
const rows = [...document.querySelectorAll(".sample-row")];
const guides = treeGuides(rows.map((row) => ({ depth: Number(row.dataset.depth) })));
rows.forEach((row, index) => {
  const branches = document.createDocumentFragment();
  appendTreeGuides(branches, guides[index]);
  row.prepend(branches);
});
