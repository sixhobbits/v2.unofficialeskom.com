---
slug: eskom-april-data
title: "Eskom Data: April 2025"
authors: [gareth]
date: 2025-05-08
---

Eskom April data 🔋🔌💡

Note: the sqlite databases that all the metabase queries are based on are now available for direct download at [unofficialeskom.com/dashboards/#...](https://unofficialeskom.com/dashboards/#data). I still have a TODO to create a data dictionary and explain the columns etc, but it's pretty straight forward.

🧵

{/* truncate */}

EAF is not looking good with total loss at the highest level since March 2024.

Silver lining is that April is actually probably better last month - reduction in unplanned outages and an increase in planned outages, leads to higher total outages, but still better than more unplanned outages.

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreiacfnbu6ynqpi5xv5e3t6efmsarh4gno7dh2zs4zcmeqzdroh75ky)

coal slightly down again.

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreib2vfk26nqzhou2iycwqqsufyqh7fi4ov6zjydiba7lc7vqwdqsze)

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreidmgn6agf4bmci3otgcakkqkzwwaum5ofq2ql4a6okvldkc4lpx44)

Last month ([bsky.app/profile/sixh...](https://bsky.app/profile/sixhobbits.bsky.social/post/3llqyfm52t22i)) I wrote that we installed a small amount of new wind capacity for the first time in a long time.

The newer data that they released shows it coming online in April instead of March

I wasted time coming through the CSV data downloads to make sure it wasn't a bug

They've taken their foot off the diesel a bit, but we're still using a lot. Peaking at 3GW (more than 3 Koebergs) and averaging 600 MW (close to one unit of Kusile, 800 MW x 6 units, [en.wikipedia.org/wiki/Kusile_...](https://en.wikipedia.org/wiki/Kusile_Power_Station)).

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreic5kmdbhkvkwsbivg4kzazopw6thiiiz5m5rjvnj4vyvsqbsp257y)

I also added Interruptible Load Shed as a tracked graph for the first time after **@c4talyst.bsky.social** mentioned it was peaking.

This is a weird mechanism where Eskom can create virtual capacity by shutting off demand separate from loadshedding. 

I haven't figured out what the numbers mean yet.

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreifbqzdmnaqcb7gabhvrtpfdwz6w6lopcp24bacsidtpveyjxl3xne)

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreig4hpuld5vpkxlbp46itasfbejqj36d44yefyq2tksmf6s4uaifqa)

The other graphs are averages of the data I get from Eskom, but ILS seems very short lived, so all the 0s created weirdly small numbers (averaged by hour). This graph shows the total instead but that also doesn't seem right.

Whatever it is, they're using more of it than they have in a while.

I'm also tracking IOS (interruption of supply) now, which is similar but where they can turn off specific big business customers if they need. They haven't been squeezing more out of this than usual recently though.

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreielx4sutv2aajldorqkvti556iwcn7zswhzpvjdylrbza5ckasfke)

Exports are continuing to decline from their weird peak a few months ago

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreiayufsqak7zkwzgsdkmoj5fhqdbofqvs5k2lmfzfviw3rd3bnax3a)

Our hydro plant is working again. I don't understand this cycle either, but it seems to vary quite a lot. Either way, it's not much power so not that important, but I'm curious what leads to these swings.

![chart](https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:nrgklo4jfeofuhg2x7ta5p6x/bafkreicbryowocnxze4is73vleusl6mjgbue6znddr26kmv3butgzrrzpu)

See [unofficialeskom.com](https://unofficialeskom.com) for more and let me know any questions or comments.

The update this month was late because I didn't get the normal file after asking for it. Shout out to Yegz for sharing it with me. Maybe they blocked my email or something
