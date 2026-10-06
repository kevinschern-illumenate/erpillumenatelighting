import {
  PDFName,
  PDFOperator,
  PDFOperatorNames,
  PDFString,
  type PDFDocument,
  type PDFPage,
} from '@cantoo/pdf-lib';

export function createLayers(document: PDFDocument, names: string[]) {
  const refs = names.map((name) =>
    document.context.register(document.context.obj({ Type: 'OCG', Name: PDFString.of(name) })),
  );
  document.catalog.set(
    PDFName.of('OCProperties'),
    document.context.obj({ OCGs: refs, D: { Order: refs, ON: refs, BaseState: 'ON' } }),
  );
  return (page: PDFPage, index: number) => {
    const properties = document.context.obj(
      Object.fromEntries(refs.map((ref, i) => [`OC${i}`, ref])),
    );
    page.node.normalizedEntries().Resources.set(PDFName.of('Properties'), properties);
    return PDFOperator.of(PDFOperatorNames.BeginMarkedContentSequence, [
      PDFName.of('OC'),
      PDFName.of(`OC${index}`),
    ]);
  };
}
