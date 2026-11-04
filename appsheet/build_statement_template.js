// Builds Customer_Statement_Template.docx for the AppSheet "Customer Statement" bot.
// Upload the .docx to Google Drive, open as Google Docs, and pick it as the bot's template.
const fs=require('fs');
const path=require('path');
const {Document,Packer,Paragraph,TextRun,Table,TableRow,TableCell,WidthType,AlignmentType,ShadingType,BorderStyle,Footer,PageNumber,VerticalAlign}=require('docx');
const F="Arial", NAVY="1F3864", LIGHT="E8EEF7", GOLD="FFF4D6", GREY="666666";
const R=AlignmentType.RIGHT, C=AlignmentType.CENTER;
const t=(s,o={})=>new TextRun({text:s,font:F,size:o.size||17,bold:o.bold,color:o.color,italics:o.it});
const p=(runs,o={})=>new Paragraph({alignment:o.align,spacing:{before:o.before||0,after:o.after??40},children:runs});
const none={style:BorderStyle.NONE,size:0,color:"FFFFFF"};
const thin={style:BorderStyle.SINGLE,size:4,color:"BFC9D9"};
const cell=(content,w,o={})=>new TableCell({width:{size:w,type:WidthType.DXA},verticalAlign:VerticalAlign.CENTER,
  shading:o.fill?{type:ShadingType.CLEAR,fill:o.fill,color:"auto"}:undefined,
  borders:o.noborder?{top:none,bottom:none,left:none,right:none}:{top:thin,bottom:thin,left:thin,right:thin},
  margins:{top:70,bottom:70,left:90,right:90},
  children:Array.isArray(content)?content:[p([t(content,{bold:o.bold,size:o.size||15,color:o.color})],{align:o.align,after:0})]});
const tbl=(w,rows)=>new Table({width:{size:w.reduce((a,b)=>a+b),type:WidthType.DXA},columnWidths:w,rows});
const hdr=(w,labels,al=[])=>new TableRow({tableHeader:true,children:labels.map((l,i)=>cell(l,w[i],{bold:true,fill:NAVY,color:"FFFFFF",align:al[i]}))});
const section=s=>new Paragraph({spacing:{before:280,after:100},border:{bottom:{style:BorderStyle.SINGLE,size:8,color:NAVY,space:3}},children:[t(s.toUpperCase(),{bold:true,size:19,color:NAVY})]});
const sumT=c=>`<<SUM(SELECT([Related Transactions][Amount], ${c}))>>`;
const mrpSales='<<SUM(SELECT([Related Transactions][MRP Value], [Txn Type] = "Sale"))>>';

// Header
const header=tbl([6200,4266],[new TableRow({children:[
 cell([p([t("<<ANY(Settings[Company Name])>>",{bold:true,size:30,color:NAVY})],{after:40}),
       p([t("Your address line here",{size:16,color:GREY})],{after:10}),
       p([t("Phone: 00000 00000  ·  Email: you@example.com  ·  GSTIN: ________",{size:16,color:GREY})],{after:0})],6200,{noborder:true}),
 cell([p([t("STATEMENT OF ACCOUNT",{bold:true,size:24,color:NAVY})],{align:R,after:60}),
       p([t("Date: ",{size:16,color:GREY}),t("<<TODAY()>>",{bold:true,size:16})],{align:R,after:10}),
       p([t("Customer ID: ",{size:16,color:GREY}),t("<<[Customer ID]>>",{bold:true,size:16})],{align:R,after:0})],4266,{noborder:true})]})]);
const rule=new Paragraph({spacing:{before:80,after:160},border:{bottom:{style:BorderStyle.SINGLE,size:18,color:NAVY,space:1}},children:[]});

// Customer box + balance due
const billTo=tbl([5233,5233],[new TableRow({children:[
 cell([p([t("STATEMENT FOR",{bold:true,size:14,color:GREY})],{after:40}),
       p([t("<<[Customer Name]>>",{bold:true,size:20})],{after:30}),
       p([t("<<[Address]>>",{size:16})],{after:10}),
       p([t("Phone: <<[Phone]>>   ·   Area: <<[Area]>>",{size:16})],{after:0})],5233,{fill:LIGHT}),
 cell([p([t("BALANCE DUE",{bold:true,size:14,color:GREY})],{align:R,after:40}),
       p([t("₹ <<[Balance]>>",{bold:true,size:34,color:NAVY})],{align:R,after:30}),
       p([t("Last payment: <<[Last Payment Date]>>",{size:15,color:GREY})],{align:R,after:0})],5233,{fill:GOLD})]})]);

// Account summary
const sw=[7466,3000];
const sRow=(a,b,o={})=>new TableRow({children:[cell(a,sw[0],{bold:o.bold,fill:o.fill,color:o.color}),cell(b,sw[1],{align:R,bold:o.bold,fill:o.fill,color:o.color})]});
const summary=tbl(sw,[
 sRow("Total Sales at MRP",mrpSales,{color:GREY}),
 sRow("Invoice Discount (MRP − Billed)","<<[MRP Sales (Total)] - [Sales Billed (Total)]>>",{color:GREY}),
 sRow("TOD / JV Discount",sumT(`[Txn Type] = "JV"`),{color:GREY}),
 sRow("Total Discount (<<[Discount %]>> of MRP)","<<[Discount Amount]>>",{bold:true,color:GREY}),
 sRow("Opening Balance",sumT(`[Txn Type] = "Opening Balance"`)),
 sRow("Add: Total Sales (Billed)",sumT(`[Txn Type] = "Sale"`)),
 sRow("Less: Stock Returns",sumT(`[Txn Type] = "Stock Return"`)),
 sRow("Less: TOD / JV",sumT(`[Txn Type] = "JV"`)),
 sRow("Less: Total Payments Received",sumT(`[Txn Type] = "Payment"`)),
 sRow("BALANCE DUE (₹)","<<[Balance]>>",{bold:true,fill:GOLD})]);

// Brand-wise (loops over the Brands this customer uses; Stmt columns live on Brands)
const bw=[2266,1800,1100,1700,1700,1900];
const brandTbl=tbl(bw,[hdr(bw,["Brand","Sales at MRP (₹)","Disc %","Billed (₹)","Payments (₹)","Balance (₹)"],[undefined,R,R,R,R,R]),
 new TableRow({children:[cell('<<Start: SELECT(Brands[Brand], [Stmt Used])>><<[Brand]>>',bw[0],{bold:true}),
  cell("<<[Stmt MRP]>>",bw[1],{align:R}),cell("<<[Stmt Discount %]>>",bw[2],{align:R}),cell("<<[Stmt Sales]>>",bw[3],{align:R}),
  cell("<<[Stmt Payments]>>",bw[4],{align:R}),cell("<<[Stmt Balance]>><<End>>",bw[5],{align:R,bold:true})]}),
 new TableRow({children:[cell("TOTAL",bw[0],{bold:true,fill:LIGHT}),cell(mrpSales,bw[1],{bold:true,fill:LIGHT,align:R}),
  cell("<<[Discount %]>>",bw[2],{bold:true,fill:LIGHT,align:R}),cell(sumT(`[Txn Type] = "Sale"`),bw[3],{bold:true,fill:LIGHT,align:R}),
  cell(sumT(`[Txn Type] = "Payment"`),bw[4],{bold:true,fill:LIGHT,align:R}),cell("<<[Balance]>>",bw[5],{bold:true,fill:LIGHT,align:R})]})]);

// Transactions
const xw=[1250,1550,1200,1366,1450,950,1350,1350];
const txTbl=tbl(xw,[hdr(xw,["Date","Brand","Type","Invoice No","MRP (₹)","Disc %","Debit (₹)","Credit (₹)"],[undefined,undefined,undefined,undefined,R,R,R,R]),
 new TableRow({children:[cell('<<Start: ORDERBY([Related Transactions], [Date])>><<[Date]>>',xw[0]),cell("<<[Brand]>>",xw[1]),cell("<<[Txn Type]>>",xw[2]),
  cell("<<[Invoice No]>>",xw[3]),cell("<<[MRP Value]>>",xw[4],{align:R}),cell("<<[Discount %]>>",xw[5],{align:R}),
  cell("<<[Debit]>>",xw[6],{align:R}),cell("<<[Credit]>><<End>>",xw[7],{align:R})]}),
 new TableRow({children:[cell("TOTAL",xw[0],{bold:true,fill:LIGHT}),...[1,2,3].map(i=>cell("",xw[i],{fill:LIGHT})),
  cell(mrpSales,xw[4],{bold:true,fill:LIGHT,align:R}),cell("<<[Discount %]>>",xw[5],{bold:true,fill:LIGHT,align:R}),
  cell("<<SUM([Related Transactions][Debit])>>",xw[6],{bold:true,fill:LIGHT,align:R}),cell("<<SUM([Related Transactions][Credit])>>",xw[7],{bold:true,fill:LIGHT,align:R})]})]);

// Bank details (no Cash)
const kw=[1900,1700,2100,2066,1400,1300];
const bankTbl=tbl(kw,[hdr(kw,["Brand","Bank","Account Name","Account No","IFSC","UPI"]),
 new TableRow({children:[cell('<<Start: SELECT(Brands[Brand], AND([Stmt Used], NOT(CONTAINS([Brand], "Cash"))))>><<[Brand]>>',kw[0],{bold:true}),
  cell("<<[Bank Name]>>",kw[1]),cell("<<[Account Name]>>",kw[2]),cell("<<[Account No]>>",kw[3]),cell("<<[IFSC]>>",kw[4]),cell("<<[UPI]>><<End>>",kw[5])]})]);

const sign=tbl([5233,5233],[new TableRow({children:[
 cell([p([t("Thank you for your business.",{it:true,size:16,color:GREY})],{after:0})],5233,{noborder:true}),
 cell([p([t("For <<ANY(Settings[Company Name])>>",{bold:true,size:16})],{align:R,after:500}),
       p([t("Authorised Signatory",{size:15,color:GREY})],{align:R,after:0})],5233,{noborder:true})]})]);

const footer=new Footer({children:[new Paragraph({alignment:C,children:[
 t("This is a computer-generated statement. Please report any difference within 7 days.   ·   Page ",{size:13,color:GREY}),
 new TextRun({children:[PageNumber.CURRENT],font:F,size:13,color:GREY}),t(" of ",{size:13,color:GREY}),
 new TextRun({children:[PageNumber.TOTAL_PAGES],font:F,size:13,color:GREY})]})]});

const doc=new Document({sections:[{properties:{page:{margin:{top:720,bottom:900,left:720,right:720}}},footers:{default:footer},children:[
 header,rule,billTo,
 section("Account Summary"),summary,
 section("Brand-wise Summary"),brandTbl,
 section("Transaction Details"),txTbl,
 section("Bank Details for Payment"),bankTbl,
 new Paragraph({spacing:{after:300},children:[]}),sign]}]});
Packer.toBuffer(doc).then(b=>{fs.writeFileSync(path.join(__dirname,'Customer_Statement_Template.docx'),b);console.log('ok')});
