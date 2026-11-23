// Shared branch geometry for the editor and source picker.
export function treeGuides(rows) {
  // Only visible siblings keep a branch open; collapsed/hidden descendants
  // should not leave dangling guide lines in the editor.
  const hasNextSibling = rows.map(() => false);
  const previousAtDepth = [];
  rows.forEach((row, index) => {
    previousAtDepth.length = row.depth + 1;
    const previous = previousAtDepth[row.depth];
    if (previous !== undefined) hasNextSibling[previous] = true;
    previousAtDepth[row.depth] = index;
  });
  const trail = [];
  return rows.map((row, index) => {
    trail.length = row.depth;
    if (row.depth) trail[row.depth - 1] = hasNextSibling[index];
    const guides = trail.map((continues, level) => {
      if (level === row.depth - 1) return continues ? "branch" : "branch last";
      return continues ? "trunk" : "";
    });
    return guides;
  });
}

export function appendTreeGuides(item, guides) {
  for (const guide of guides) {
    const indent = document.createElement("span");
    indent.className = `indent ${guide}`;
    indent.setAttribute("aria-hidden", "true");
    item.appendChild(indent);
  }
}
