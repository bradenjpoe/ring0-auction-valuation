## Overview
I included 3 interactive visuals at the bottom of this page below based on Keeneland Sept Yearling sales data from 2018-2024. *Yearly Sales Data* shows how sires have performed YoY while the interactive data table allows you to look at all line-item sales - the middle chart will have a more in depth explanation. I'll do more work on individual purchasers and sellers at auctions next while also cleaning and integrating OBS breeze data. 

I'd like to build a model that can estimate the price of a 2yo in the OBS sale based on their breeze time along with yearling sales prices, family performance, etc. The OBS results could then be fed back into another model predicting yearling sales, which creates a constantly improving feedback loop that adjusts in real-time. 

[Racing Squared](https://racingsquared.com/) is an example of what's possible: they use pose estimation and computer vision to assess a horse's conformation automatically in addition to all data points I mentioned above. This is an area I've worked in before and fortunately Keeneland/OBS/etc all post walking videos of their horses, so building a similar conformation-based AI tool is do-able given time.
