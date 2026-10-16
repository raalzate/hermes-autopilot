import {Circle, Layout, Rect, Txt, makeScene2D} from '@motion-canvas/2d';
import {
  all, createRef, createSignal, easeInOutCubic, easeOutBack, makeRef, waitFor, Reference,
} from '@motion-canvas/core';

// Una tarea de punta a punta: quién trabaja en cada paso, qué escribe la consola y qué decide el arnés.
// Es el mismo guion de la consola de la portada; si cambia uno, se cambia el otro.

const PAPEL = '#eeeff4', TINTA = '#141824', SUAVE = '#485063', FAINT = '#7d8599', RAYA = '#cdd1de';
const ACENTO = '#4b3fb0', VERDE = '#1e7a3c', ROJO = '#b3261e', OCRE = '#8a6d2b';
const TERM = '#11141d', TERM_TX = '#cbd2e0';
const SANS = 'Helvetica Neue, Arial, sans-serif', MONO = 'Menlo, Consolas, monospace';

type Tipo = 'cmd' | 'paso' | 'voz' | 'accion' | 'freno' | 'motivo' | 'alerta' | 'rojo' | 'verde' | 'fin';
type Estado = 'idle' | 'frena' | 'aprueba' | 'verde';
const COLOR: Record<Tipo, string> = {
  cmd: '#9fbaf5', paso: '#8f97ab', voz: '#c9cfdc', accion: '#8fd3a3', freno: '#ef8a80', motivo: '#e9c6c2',
  alerta: '#d3ae5e', rojo: '#ef8a80', verde: '#5cc47c', fin: '#7ddc98',
};
const ESTADO: Record<Estado, {c: string; t: string}> = {
  idle: {c: ACENTO, t: 'vigilando…'}, frena: {c: ROJO, t: '✗ bloqueó'}, aprueba: {c: OCRE, t: '? pide aprobación'}, verde: {c: VERDE, t: '✓ verde'},
};

const ACTORES = [
  {id: 'persona', n: 'Equipo', s: 'chat · correo'},
  {id: 'local', n: 'Modelo local', s: 'capa inteligente'},
  {id: 'hermes', n: 'Hermes', s: 'manos · rama aislada'},
  {id: 'claude', n: 'Claude', s: 'código y revisión'},
  {id: 'mcp', n: 'Integraciones', s: 'mínimo privilegio'},
  {id: 'gate', n: 'Gate', s: 'verde o rojo'},
  {id: 'senior', n: 'Senior', s: 'juzga y firma'},
];

const PASOS: {a: number; t: string; nota: string; l: [Tipo, string, Estado?][]}[] = [
  {a: 0, t: 'Pide la tarea', nota: 'Por chat o correo. Hermes la convierte en una tarea de la cola.',
    l: [['cmd', 'chat › equipo: Arreglá el bug del issue #42 y dejalo en un PR'], ['accion', '✓ tarea en la cola · .hermes/loop/tasks.md']]},
  {a: 1, t: 'Explora y planea', nota: 'El modelo local lee el repo y prepara el plan. Los datos no salen de la caja.',
    l: [['paso', '▶ modelo local · explora y planea'], ['accion', '[read_file] ✓ src/fechas.py'], ['voz', '«parse_fecha() revienta con una fecha vacía. Plan: test, arreglo, gate.»']]},
  {a: 2, t: 'Rama aislada y un freno', nota: 'Antes de cada llamada el plugin decide: pasa, pide aprobación o bloquea con el porqué.',
    l: [['paso', '▶ hermes · rama aislada loop/issue-42'], ['voz', '«para ver cómo conecta, leo el .env»'], ['cmd', 'agente → read_file {"path": ".env"}'],
      ['freno', '✗ block · LECTURA PROTEGIDA: `.env` no lo lee el agente.', 'frena'], ['motivo', '  Motivo: tiene los secretos. Leé .env.example o pedíla al humano.'], ['accion', '[read_file] ✓ .env.example']]},
  {a: 3, t: 'Claude escribe el código', nota: 'Hermes le delega lo difícil, con herramientas y turnos acotados. Mismos frenos.',
    l: [['paso', '▶ claude (delegado) · tools acotadas · tope de turnos'], ['accion', '[write_file] ✓ tests/test_fechas.py'], ['accion', '[write_file] ✓ src/fechas.py']]},
  {a: 4, t: 'Consulta afuera', nota: 'Tras leer a un tercero, lo que tenga efecto afuera lo decide una persona.',
    l: [['accion', '[mcp__github__issue_get] ✓ declarada · solo lectura'], ['cmd', 'agente → mcp__correo__send_email {"to": "cliente@…"}'],
      ['alerta', '? approve · la sesión leyó a un tercero: lo decide un humano', 'aprueba']]},
  {a: 5, t: 'El gate decide', nota: 'Un comando decide «terminado». Rojo distinto: reintenta. El mismo rojo dos veces: escala.',
    l: [['paso', '▶ intento 1 · el gate verifica'], ['rojo', '✗ intento 1: rojo — test_fecha_vacia', 'frena'], ['paso', '▶ intento 2 · reintento con el rojo en mano'],
      ['accion', '[write_file] ✓ src/fechas.py'], ['verde', '✓ intento 2: verde', 'verde']]},
  {a: 3, t: 'Revisa el diff', nota: 'Un revisor inferencial busca lo que ninguna regla vio. Está medido, no a ojo.',
    l: [['paso', '▶ revisor inferencial · Claude lee el diff'], ['verde', '✓ sin atajos: ningún test silenciado ni cambio fuera de la tarea', 'verde']]},
  {a: 6, t: 'Juzga y firma', nota: 'El senior juzga y firma. El agente no se firma ni fusiona a main.',
    l: [['fin', '✓ LISTO PARA REVISIÓN — gate verde en el intento 2', 'verde'], ['accion', 'PR #43 abierto · espera la firma del senior'], ['paso', 'no fusiona a main · no cambia sus permisos']]},
];

export default makeScene2D(function* (view) {
  view.fill(PAPEL);

  const cx = (i: number) => -810 + i * 270;
  const actores: Rect[] = [];
  const subs: Txt[] = [];
  const estado = createSignal<Estado>('idle');
  const barra = createRef<Rect>();
  const estTxt = createRef<Txt>();
  const term = createRef<Layout>();
  const nota = createRef<Txt>();
  const titulo = createRef<Txt>();
  const ficha = createRef<Circle>();
  const marcas: Circle[] = [];

  view.add(
    <>
      <Txt text="Una tarea, de punta a punta, con todo junto" fontFamily={SANS} fontWeight={700} fontSize={46} fill={TINTA} x={-960 + 90} y={-470} offsetX={-1} />
      <Txt ref={titulo} text="" fontFamily={MONO} fontSize={26} fill={ACENTO} x={960 - 90} y={-470} offsetX={1} />
      {ACTORES.map((a, i) => (
        <Rect ref={makeRef(actores, i)} x={cx(i)} y={-330} width={240} height={150} radius={14} fill="#fff" stroke={RAYA} lineWidth={3} opacity={0.5} layout direction="column" alignItems="center" justifyContent="center" gap={6}>
          <Txt text={a.n} fontFamily={SANS} fontWeight={700} fontSize={30} fill={TINTA} />
          <Txt ref={makeRef(subs, i)} text={a.s} fontFamily={MONO} fontSize={19} fill={FAINT} />
        </Rect>
      ))}
      <Circle ref={ficha} size={26} fill={ACENTO} x={cx(0)} y={-230} opacity={0} />
      <Rect ref={barra} y={-130} width={1740} height={84} radius={12} stroke={() => ESTADO[estado()].c} lineWidth={4} fill="#fff" layout alignItems="center" padding={[0, 32]} justifyContent="space-between">
        <Txt text="Arnés · cada llamada pasa por los frenos" fontFamily={MONO} fontSize={28} fill={ACENTO} />
        <Txt ref={estTxt} text="vigilando…" fontFamily={MONO} fontWeight={700} fontSize={28} fill={() => ESTADO[estado()].c} />
      </Rect>
      <Rect y={205} width={1740} height={440} radius={14} fill={TERM} />
      <Layout ref={term} offset={[-1, -1]} x={-870 + 40} y={205 - 220 + 28} layout direction="column" gap={10} alignItems="start" />
      <Txt ref={nota} text="" fontFamily={SANS} fontSize={32} fill={SUAVE} y={470} width={1740} textAlign="center" />
      {PASOS.map((_, i) => <Circle ref={makeRef(marcas, i)} size={16} fill={RAYA} x={-(PASOS.length - 1) * 14 + i * 28} y={520} />)}
    </>,
  );

  const iluminar = function* (i: number) {
    yield* all(...actores.map((r, j) =>
      all(r.opacity(j === i ? 1 : r.opacity() > 0.9 ? 0.85 : r.opacity(), 0.35),
        r.stroke(j === i ? ACENTO : RAYA, 0.35),
        r.scale(j === i ? 1.07 : 1, 0.35, easeOutBack),
        r.fill(j === i ? '#e6e3fa' : '#fff', 0.35))));
  };

  for (let k = 0; k < PASOS.length; k++) {
    const p = PASOS[k];
    titulo().text(`${k + 1}/${PASOS.length} · ${p.t}`);
    yield* all(
      iluminar(p.a),
      ficha().position.x(cx(p.a), 0.6, easeInOutCubic),
      ficha().opacity(1, 0.3),
      term().children().length ? term().opacity(0, 0.25) : waitFor(0),
      nota().opacity(0, 0.2),
    );
    term().removeChildren();
    term().opacity(1);
    nota().text(p.nota);
    estado('idle');
    estTxt().text('vigilando…');
    yield* nota().opacity(1, 0.3);

    for (const [tipo, txt, est] of p.l) {
      const t = createRef<Txt>();
      term().add(<Txt ref={t} text="" fontFamily={MONO} fontSize={30} fill={COLOR[tipo]} fontWeight={tipo === 'freno' || tipo === 'fin' ? 700 : 400} />);
      yield* t().text(txt, Math.min(1.2, 0.25 + txt.length * 0.012), easeInOutCubic);
      if (est) {
        estado(est);
        estTxt().text(ESTADO[est].t);
        if (est === 'frena') yield* all(barra().x(-10, 0.06).to(10, 0.06).to(-6, 0.06).to(0, 0.06));
      }
      yield* waitFor(0.45);
    }
    marcas[k].fill(VERDE);
    yield* waitFor(1);
  }
  yield* waitFor(2.5);
});
