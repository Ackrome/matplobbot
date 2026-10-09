/* Small uncompressed ZIP writer: UTF-8 names, bounded exports, no CDN dependency. */
(() => {
    const encoder=new TextEncoder();
    const table=Uint32Array.from({length:256},(_,n)=>{for(let k=0;k<8;k++)n=(n&1)?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
    function crc32(bytes){let crc=0xffffffff;for(const b of bytes)crc=table[(crc^b)&255]^(crc>>>8);return(crc^0xffffffff)>>>0;}
    function safePath(value){return String(value).split(/[\\/]+/).filter(p=>p&&p!=='.'&&p!=='..').map(p=>p.replace(/[\x00-\x1f:*?"<>|]/g,'_')).join('/')||'file';}
    function zip(files){
        const local=[],central=[];let offset=0,size=0;const seen=new Set();
        if(files.length>60000)throw new Error('Archive has too many files');
        for(const file of files){
            const path=safePath(file.name);if(seen.has(path))throw new Error('Duplicate archive path');seen.add(path);
            const name=encoder.encode(path),data=file.bytes instanceof Uint8Array?file.bytes:encoder.encode(file.text||'');size+=data.length;if(size>128*1024*1024||name.length>65535)throw new Error('Archive is too large');
            const crc=crc32(data),header=new Uint8Array(30),h=new DataView(header.buffer);h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);h.setUint16(6,0x800,true);h.setUint32(14,crc,true);h.setUint32(18,data.length,true);h.setUint32(22,data.length,true);h.setUint16(26,name.length,true);
            local.push(header,name,data);const entry=new Uint8Array(46),v=new DataView(entry.buffer);v.setUint32(0,0x02014b50,true);v.setUint16(4,20,true);v.setUint16(6,20,true);v.setUint16(8,0x800,true);v.setUint32(16,crc,true);v.setUint32(20,data.length,true);v.setUint32(24,data.length,true);v.setUint16(28,name.length,true);v.setUint32(42,offset,true);central.push(entry,name);offset+=header.length+name.length+data.length;
        }
        const end=new Uint8Array(22),v=new DataView(end.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,files.length,true);v.setUint16(10,files.length,true);v.setUint32(12,central.reduce((s,x)=>s+x.length,0),true);v.setUint32(16,offset,true);return new Blob([...local,...central,end],{type:'application/zip'});
    }
    function download(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}
    window.MpbArchive={zip,download,safePath};
})();
