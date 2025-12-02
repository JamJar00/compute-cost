# Compute Cost
This is a WIP project to show the costs of different AWS compute types in pretty graphs and demonstrate how their cost changes as each scales up. Hopefully it will help people choose the right option for their project and understand the limitations of each

## Development
At some point I'll have this hosted on the internet. For now, run it locally with:
```bash
npm install
npm run dev -- --open
```

## TODO
- Consider AWS Free Tier in costs
- Add EC2 somehow (EC2 scales linearly vertically so can just consider bottom tier and a few different types?)
- Automatically update costs from the AWS API
- Add learn more section
- Add tips for each compute type
