<script>
  import Chart from 'chart.js/auto';

  function estimateLambdaCost(rps, mem, time) {
    const gbSeconds = rps * (mem / 1024) * (time / 1000);
    const gbSecondsPerMonth = gbSeconds * 60 * 60 * 730;
    const durationCost = Math.min(gbSecondsPerMonth, 6000000000) * 0.0000166667
                          + Math.min(Math.max(0, gbSecondsPerMonth - 6000000000), 9000000000) * 0.000015
                          + Math.max(0, gbSecondsPerMonth - 15000000000) * 0.0000133334;

    const requestsPerMonth = rps * 60 * 60 * 730;
    const requestCost = requestsPerMonth / 1000000 * 0.20;

    return durationCost + requestCost;
  }

  function estimateFargateCost(rps, mem, rpsCpu) {
    return (Math.ceil(mem / 1024) * 0.00511 + Math.ceil(rps / rpsCpu) * 0.04656) * 730;
  }

  function estimateFargateSpotCost(rps, mem, rpsCpu) {
    return (Math.ceil(mem / 1024) * 0.00167115 + Math.ceil(rps / rpsCpu) * 0.01521889) * 730;
  }

  function estimateEc2Cost(rps, rpsCpu) {
    // c5.large instances have two CPUs so we double rpsCpu
    return Math.ceil(rps / (rpsCpu * 2)) * 0.101 * 730
  }

  let rps = $state(10), mem = $state(1024), time = $state(100), rpsCpu = $state(10);
  let lambdaCost = $derived(estimateLambdaCost(rps, mem, time));
  let fargateCost = $derived(estimateFargateCost(rps, mem, rpsCpu));
  let fargateSpotCost = $derived(estimateFargateSpotCost(rps, mem, rpsCpu));
  let ec2Cost = $derived(estimateEc2Cost(rps, rpsCpu));

  let canvas;
  let chart;
  $effect(() => {
    if (canvas) {
      chart = new Chart(
        canvas,
        {
          type: 'bar',
          data: null,
          options: {
            scales: {
              y: {
                title: {
                  display: true,
                  text: "Cost Per Month ($)"
                }
              }
            }
          }

        }
      );
    }
  });

  $effect(() => {
    const chartData = [
      { name: "Lambda", cost: lambdaCost },
      { name: "Fargate (On Demand)", cost: fargateCost },
      { name: "Fargate (Spot)", cost: fargateSpotCost },
      { name: "EC2 (On Demand, C5 Instances)", cost: ec2Cost },
    ];

    chart.data = {
      labels: chartData.map(row => row.name),
      datasets: [
        {
          label: 'Cost per Month',
          data: chartData.map(row => row.cost)
        }
      ]
    };
    chart.update();
  });

  let detailPage = $state("lambda");

  let scalingCanvas;
  let scalingChart;
  $effect(() => {
    if (scalingCanvas) {
      scalingChart = new Chart(
        scalingCanvas,
        {
          type: 'line',
          data: null,
          options: {
            scales: {
              x: {
                title: {
                  display: true,
                  text: "Requests per Second"
                }
              },
              y: {
                title: {
                  display: true,
                  text: "Cost per Month ($)"
                }
              }
            }
          }
        }
      );
    }
  });

  $effect(() => {
    const steps = [0.125, 0.25, 0.5, 1, 2, 4, 8];
    const lambdaChartData = steps.map(s => ({ rps: rps * s, cost: estimateLambdaCost(rps * s, mem, time) }));
    const fargateChartData = steps.map(s => ({ rps: rps * s, cost: estimateFargateCost(rps * s, mem, rpsCpu) }));
    const fargateSpotChartData = steps.map(s => ({ rps: rps * s, cost: estimateFargateSpotCost(rps * s, mem, rpsCpu) }));
    const ec2ChartData = steps.map(s => ({ rps: rps * s, cost: estimateEc2Cost(rps * s, rpsCpu) }));

    scalingChart.data = {
      labels: lambdaChartData.map(row => row.rps),
      datasets: [
        {
          label: 'Lambda',
          data: lambdaChartData.map(row => row.cost)
        },
        {
          label: 'Fargate (On Demand)',
          stepped: 'after',
          data: fargateChartData.map(row => row.cost)
        },
        {
          label: 'Fargate (Spot)',
          stepped: 'after',
          data: fargateSpotChartData.map(row => row.cost)
        },
        {
          label: 'EC2 (On Demand, C5 Instances)',
          stepped: 'after',
          data: ec2ChartData.map(row => row.cost)
        }
      ]
    };
    scalingChart.update();
  });
</script>

<h1>Compute Cost</h1>
<p>This calculator is designed to help you evaluate the different options of compute in AWS. It demonstrates how each scales with cost and helps you find the point at which other deployment technologies may become more cost efficient.</p>
<p><i>The tool is designed primarily for APIs. It assumes Linux x86 instances in London. Pricing correct at the time of writing (2025-12-02). Spot pricing is almost certainly different now. Check and double check your cost estimates with the AWS pricing calculator before you make decisions. Do not rely on this tool for accuracy. If you make bad decisions they're your fault not mine.</i></p>

<section>
  <h2>Parameters</h2>
  <div class="input-section">
    <div class="input-block">
      <h4>Expected requests per second</h4>
      <p>
        <label for="rps">This is the number of requests you expect to process every second, on average.</label>
      </p>
      <input id="rps" type="number" bind:value={rps} /> <label for="rps">requests/s</label>
    </div>

    <div class="input-block">
      <h4>Expected memory usage</h4>
      <p>
        <label for="mem">The maximum amount of memory you expect to require</label>
      </p>
      <input id="mem" type="number" bind:value={mem} /> <label for="mem">MB</label>
    </div>

    <div class="input-block">
      <h4>Expected request time</h4>
      <p>
        <label for="mem">The amount of time you expect to spend handling each request on average. This is roughly equivalent to the latency you see from the client</label>
      </p>
      <input id="time" type="number" bind:value={time} /> <label for="time">ms</label>
    </div>

    <div class="input-block">
      <h4>Expected requests per second per CPU</h4>
      <p>
        <label for="mem">The number of requests that can be processed per second on a single CPU. We assume scaling CPUs scales the number of requests linearly but shared resources will impact this</label>
      </p>
      <input id="rpsCpu" type="number" bind:value={rpsCpu} /> <label for="rpsCpu">requests/s</label>
    </div>
  </div>
</section>

<section>
  <h2>Cost</h2>
  <p>Expected costs are listed in USD per month (730 hours)
  <div class="costs-section">
    <table class="costs-table">
      <tbody>
        <tr><td>Lambda</td><td>${lambdaCost.toFixed(2)}</td></tr>
        <tr><td>Fargate with On Demand instances</td><td>${fargateCost.toFixed(2)}</td></tr>
        <tr><td>Fargate with Spot instances</td><td>${fargateSpotCost.toFixed(2)}</td></tr>
      </tbody>
    </table>
    <div class="chart-block"><canvas bind:this={canvas}></canvas></div>
  </div>
</section>

<section>
  <h2>Scaling</h2>
  <p>This chart shows you how each compute option scales in cost for varying requests per second based on your other parameters.</p>
  <p>In general, you'll notice that Lambda is cheap for few requests, but there's a threshold where per instance priced options become more cost efficient</p>
  <div><canvas bind:this={scalingCanvas}></canvas></div>
</section>

<style>
  .input-section {
    display: flex;
    gap: 1em;
  }

  .input-block {
    display: block;
    flex-basis: 0;
    flex-grow: 1;

    border: black;
    border-width: 1px;
    border-style: solid;
    padding: 1em;
  }

  .costs-section {
    display: flex;
    gap: 1em;
  }

  .costs-table {
    height: fit-content;
  }

  .chart-block {
    flex-grow: 1;
  }

  h4 {
    margin-top: 0.25em;
  }

  @media (max-width: 1200px) {
    .input-section {
      flex-direction: column;
    }

    .costs-section {
      flex-direction: column;
    }
  }
</style>
