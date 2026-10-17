/** Original, hand-authored presentation metadata. No provider tracking records. */
type Labels = [string, string]
export type ReplayStory = { title: Labels; hook: Labels; context: Labels; duration: string; source: string; sourceLabel: string; note: Labels }
export const replayGallery: Record<string, ReplayStory> = {
  'last-gasp': {
    title: ['Last-second turnaround', '最后一刻的逆转'], hook: ['Two saves. A race to the other end.', '两次扑救，随即全速反击。'], duration: '20s',
    context: ['A penalty saved. A second chance denied. Eastbridge race upfield and Ellis supplies the finish.', '扑出点球，再挡补射。Eastbridge迅速反击，Ellis完成致命一击。'],
    source: 'https://www.youtube.com/watch?v=ETXv-SvOk9g&t=560s', sourceLabel: 'Watford–Leicester · 9:20',
    note: ['Inspired by Watford–Leicester, 12 May 2013.', '灵感来自2013年5月12日Watford对Leicester。'],
  },
  'one-touch': {
    title: ['Pass, move, finish', '传球、跑位、射门'], hook: ['Rowan and Vale combine to put Ellis through on goal.', 'Rowan与Vale巧妙配合，助Ellis突破防线。'], duration: '10s',
    context: ['Ellis slips away from his marker as Rowan and Vale trade quick passes to unlock the defence.', 'Rowan与Vale快速传递撕开防线，Ellis摆脱盯防完成射门。'],
    source: 'https://www.youtube.com/watch?v=c0-ZhEkEFtA&t=48s', sourceLabel: 'Brazil–Korea Republic · 0:48',
    note: ['Inspired by Richarlison’s combination goal against Korea Republic, 5 December 2022; FIFA highlights, approximately 0:48–0:58, with alternate-angle replays after it.', '灵感来自2022年12月5日Richarlison对韩国的配合进球；FIFA集锦约0:48–0:58，随后有其他角度回放。'],
  },
  breakaway: {
    title: ['From halfway to goal', '从中场直奔球门'], hook: ['Mercer leads the break. Hart races in to finish.', 'Mercer带领反击，Hart跟进完成破门。'], duration: '12s',
    context: ['West finds a way out of pressure, Mercer drives through the middle and Hart arrives to finish at the far side.', 'West在逼抢中找到出球路线，Mercer从中路突进，Hart在远端跟进破门。'],
    source: 'https://www.youtube.com/watch?v=agrGb25mJzs&t=174s', sourceLabel: 'Argentina–France · 2:54',
    note: ['Inspired by Di María’s counterattack goal in the 18 December 2022 World Cup final; FIFA extended highlights, approximately 2:54–3:05.', '灵感来自2022年12月18日世界杯决赛Di María的反击进球；FIFA加长集锦约2:54–3:05。'],
  },
}

/** Stadium coordinates, Eastbridge attacks right. Each row is squad order 01–11.
 * Visible lanes/defensive lines estimated from the linked footage; off-camera
 * players and intermediate motion are illustrative. These are not measurements.
 */
export const replayShapes: Record<string, {eastbridge: number[][][]; northport: number[][][]}> = {
  'showcase-last-gasp-v1': {
    eastbridge: [
      [[1,34],[24,8],[21,18],[21,27],[25,60],[23,44],[35,9],[24,52],[23,35],[33,44],[38,59]],
      [[9,34],[52,12],[45,24],[33,27],[54,57],[96,43],[87,11],[65,15],[92,34],[78,48],[82,59]],
    ],
    northport: [
      [[101,34],[30,15],[30,23],[30,37],[32,55],[37,29],[39,39],[11,34],[39,49],[44,19],[47,43]],
      [[103,34],[93,18],[97,29],[96,39],[91,52],[82,28],[85,40],[6,35],[76,50],[78,20],[80,59]],
    ],
  },
  'showcase-one-touch-v1': {
    eastbridge: [
      [[9,34],[65,8],[57,26],[88,46],[66,60],[82,29],[89,9],[72,48],[79,43],[85,51],[92,59]],
      [[10,34],[69,8],[63,27],[90,46],[71,59],[85,29],[94,11],[79,47],[96,33],[91,49],[97,58]],
    ],
    northport: [
      [[102,34],[91,15],[89,29],[87,40],[90,56],[80,24],[82,35],[82,49],[78,56],[67,28],[68,42]],
      [[102,35],[97,20],[96,31],[94,39],[93,51],[87,24],[89,34],[88,44],[84,54],[73,29],[76,47]],
    ],
  },
  'showcase-breakaway-v1': {
    eastbridge: [
      [[8,34],[31,8],[24,26],[25,44],[34,61],[37,31],[53,13],[49,37],[49,53],[40,48],[43,22]],
      [[10,34],[57,10],[44,27],[46,43],[58,59],[65,32],[94,23],[90,42],[77,48],[67,45],[73,20]],
    ],
    northport: [
      [[99,34],[64,16],[65,31],[61,43],[54,57],[47,27],[47,42],[42,49],[36,56],[26,26],[30,43]],
      [[101,30],[98,27],[96,36],[91,42],[83,50],[79,29],[83,40],[77,47],[66,52],[48,28],[53,43]],
    ],
  },
}
