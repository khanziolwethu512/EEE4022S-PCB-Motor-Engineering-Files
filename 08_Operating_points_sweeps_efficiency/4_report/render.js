// Renders report_content.json to a .docx: Times New Roman 11 pt, 1.5 line spacing, A4, 2.5 cm margins.
// node render.js <content.json> <out.docx>
const fs = require("fs");
const path = require("path");
const sizeOf = (p) => { const b = fs.readFileSync(p); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; };
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType,
  ImageRun, BorderStyle, ShadingType, VerticalAlign, Footer, PageNumber,
} = require("docx");
const [, , inp, out] = process.argv;
const blocks = JSON.parse(fs.readFileSync(inp, "utf8"));
const FONT = "Times New Roman";
const LINE = 360;                   // 1.5 lines
const DXA = 1440;
const TEXTW = 9026;                 // A4 width 11906 - 2 x 1440
const run = (t, o = {}) => new TextRun({ text: t, font: FONT, size: o.size || 22, bold: o.bold, italics: o.italics });
const thin = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const kids = [];
for (const b of blocks) {
  if (b.t === "note") {
    kids.push(new Paragraph({ spacing: { line: 276, after: 200 }, border: { top: thin, bottom: thin, left: thin, right: thin },
      children: [run(b.x, { italics: true, size: 20 })] }));
  } else if (b.t === "h1") {
    kids.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: kids.length > 1, spacing: { before: 240, after: 120, line: LINE },
      children: [run(b.x, { bold: true, size: 28 })] }));
  } else if (b.t === "h2") {
    kids.push(new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, spacing: { before: 200, after: 60, line: LINE },
      children: [run(b.x, { bold: true, size: 24 })] }));
  } else if (b.t === "p") {
    kids.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: LINE, after: 120 }, children: [run(b.x)] }));
  } else if (b.t === "eq") {
    kids.push(new Paragraph({ spacing: { line: LINE, before: 60, after: 60 }, tabStops: [{ type: "center", position: TEXTW / 2 }, { type: "right", position: TEXTW }],
      children: [run("\t"), run(b.x, { italics: true }), run("\t(" + b.n + ")")] }));
  } else if (b.t === "table") {
    kids.push(new Paragraph({ keepNext: true, spacing: { before: 120, after: 60, line: 276 }, children: [run(b.cap, { bold: true, size: 20 })] }));
    const tot = b.w.reduce((a, c) => a + c, 0);
    const cw = b.w.map((x) => Math.floor((x / tot) * TEXTW));
    cw[cw.length - 1] += TEXTW - cw.reduce((a, c) => a + c, 0);
    const mk = (cells, head) => new TableRow({ tableHeader: head, cantSplit: true, children: cells.map((c, i) => new TableCell({
      width: { size: cw[i], type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
      shading: head ? { type: ShadingType.CLEAR, fill: "E7E6E6", color: "auto" } : undefined,
      margins: { top: 30, bottom: 30, left: 70, right: 70 },
      borders: { top: thin, bottom: thin, left: none, right: none },
      children: [new Paragraph({ spacing: { line: 240 }, children: [run(String(c), { size: 18, bold: head })] })] })) });
    kids.push(new Table({ width: { size: TEXTW, type: WidthType.DXA }, columnWidths: cw,
      rows: [mk(b.head, true), ...b.rows.map((r) => mk(r, false))] }));
    kids.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
  } else if (b.t === "fig") {
    const s = sizeOf(b.path);
    const wpx = Math.round(b.w * 96), hpx = Math.round(wpx * s.h / s.w);
    kids.push(new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, line: 240, lineRule: "auto" },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(b.path), transformation: { width: wpx, height: hpx } })] }));
    kids.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { after: 160, line: 276 }, children: [run(b.cap, { size: 20 })] }));
  }
}
const doc = new Document({
  creator: "EEE4022S", title: "Final operating characterisation - Chapters 3-5 material",
  styles: { default: { document: { run: { font: FONT, size: 22 }, paragraph: { spacing: { line: LINE } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 28, bold: true }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 24, bold: true }, paragraph: { outlineLevel: 1 } }] },
  sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: DXA, bottom: DXA, left: DXA, right: DXA } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ font: FONT, size: 18, children: [PageNumber.CURRENT] })] })] }) },
    children: kids }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(out, buf); console.log("wrote", out); });
