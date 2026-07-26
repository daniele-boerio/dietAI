// Il minimo di markdown che i modelli usano davvero: grassetto, elenchi puntati o
// numerati, righe vuote come paragrafi. Niente libreria e niente HTML grezzo — si
// costruiscono elementi React, quindi non c'è modo di iniettare niente in pagina.
//
// Volutamente incompleto: il prompt chiede due frasi di prosa, non una pagina. Se
// serve altro (tabelle, link, codice) il problema è la risposta, non il renderer.

const BULLET = /^\s*[-•*]\s+(.*)$/;
const NUMBER = /^\s*\d+[.)]\s+(.*)$/;
const RULE = /^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/; // --- , ***, ___
const HEADING = /^#{1,6}\s*/;

// **grassetto** → <strong>. Le parti dispari dello split sono quelle fra gli asterischi.
function inline(text) {
  return text
    .split(/\*\*(.+?)\*\*/g)
    .map((parte, i) => (i % 2 ? <strong key={i}>{parte}</strong> : parte));
}

export default function ChatText({ text }) {
  const blocchi = [];
  let lista = null; // { tipo: 'ul' | 'ol', voci: [] }

  const chiudiLista = () => {
    if (!lista) return;
    const Tag = lista.tipo;
    const voci = lista.voci;
    blocchi.push(
      <Tag key={`l${blocchi.length}`}>
        {voci.map((voce, i) => (
          <li key={i}>{inline(voce)}</li>
        ))}
      </Tag>
    );
    lista = null;
  };

  for (const riga of (text || '').split('\n')) {
    if (!riga.trim() || RULE.test(riga)) {
      chiudiLista();
      continue;
    }

    const punto = riga.match(BULLET);
    const numero = punto ? null : riga.match(NUMBER);
    if (punto || numero) {
      const tipo = punto ? 'ul' : 'ol';
      if (!lista || lista.tipo !== tipo) {
        chiudiLista();
        lista = { tipo, voci: [] };
      }
      lista.voci.push((punto || numero)[1]);
      continue;
    }

    chiudiLista();
    blocchi.push(<p key={`p${blocchi.length}`}>{inline(riga.replace(HEADING, ''))}</p>);
  }
  chiudiLista();

  return <>{blocchi}</>;
}
