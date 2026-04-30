import { use } from 'echarts/core'
import { LineChart, GaugeChart, CustomChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, GaugeChart, CustomChart, GridComponent, TooltipComponent, CanvasRenderer])
