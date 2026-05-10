import { use } from 'echarts/core'
import { LineChart, GaugeChart, CustomChart, ScatterChart } from 'echarts/charts'
import { AxisPointerComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([
  LineChart,
  GaugeChart,
  CustomChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  AxisPointerComponent,
  CanvasRenderer,
])
