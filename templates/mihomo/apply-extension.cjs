'use strict';
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const context=vm.createContext({config:input,result:null});
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context,{timeout:3000});
vm.runInContext('result=main(config,"TX")',context,{timeout:3000});
process.stdout.write(JSON.stringify(context.result));
