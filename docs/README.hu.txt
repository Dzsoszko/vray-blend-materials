OBJECT BLEND 2.1.1 — Maya 2026 / V-Ray 7.x
Objektumonkénti Distance / Dirt / Distance + Dirt, mesh + proxy.

TELEPÍTÉS / FRISSÍTÉS — DRAG AND DROP
1. Töltsd le az ObjectBlend_install_2_1_1.py fájlt a gépedre.
2. Mayában legyen látható a Shelf, majd húzd a .py fájlt a viewportba.
3. Települ a felhasználói Maya scripts könyvtár object_blend_tool mappájába.
4. Az ObjectBlend shelf-fülön megjelenik a saját ikonos Object Blend gomb.
A tool a telepítés végén megnyílik. Külső képfájl vagy külön modul nem kell.

Frissítéskor az új, verziószámozott telepítőfájlt ugyanígy húzd a viewportba.
Ugyanazt a telepítési helyet és shelf-gombot frissíti, a korábbi scriptből
.py.bak biztonsági másolatot tart. A jelenet setupjait nem építi újra.
Az új verzió külön telepítő-fájlnevet kap, hogy a Maya import-cache-e ne
indítsa a régi telepítőt, ha a friss fájl másik letöltési mappában van.
A shelf-gomb mindig a telepített fájl aktuális tartalmát olvassa be.
A shelf-gomb és shelf-regisztráció mentésre kerül a Maya profiljában.

A maya_object_blend.py továbbra is futtatható a Python Script Editorban;
ez önmagában csak megnyitja a toolt. Telepítéshez a verziózott .py-t használd.

UV JELZÉS
A geometrialistában külön UV oszlop van; kijelölt sornál részletes jelzés is.
UV OK: az aktív UV setben van kiosztás minden face-en.
NO UV: nincs használható UV az aktív setben.
PARTIAL: vannak UV nélküli face-ek.
UV ?: proxy vagy nem ellenőrizhető adat; nem tekinti automatikusan UV nélkülinek.
A teljes proxy UV-ját nem ellenőrzi a preview alapján, nem konvertálja mesh-re.
Az UV OK nem UV-layout minőségellenőrzés, nem ellenőrzi az összes textúra UV-linkjét.
Az UV hiánya figyelmeztetés, nem tiltás: world-space/triplanar mapping működhet.
UV-szerkesztés után nyomd meg a Refresh gombot az újraellenőrzéshez.

ÚJ SETUP
1. Setup: New setup.
2. Jelöld ki a talajt, majd Ground > Use selected.
3. Jelöld ki a köveket / geometriákat / V-Ray proxykat.
4. + Add selection.
5. Kattints egy objektum sorára, majd állítsd a Blend módját és paramétereit.

Minden objektumnak külön maszkja és vezérlése van. A proxy összes
bekötött material-slotja ugyanahhoz az objektumvezérléshez tartozik.
Az alapértelmezés Distance. Az új objektum nem örökli a kiválasztott
régebbi objektum Dirt módját vagy egyéb paramétereit.

UTÓLAGOS HOZZÁADÁS
Válaszd ki a meglévő setupot, jelöld ki az új geometriát Mayában,
majd + Add selection. A régi lista és beállítások megmaradnak.
A már szereplő objektum ismételt hozzáadása nem duplikálja a setupját.
Remove / restore vagy Delete a fókuszban lévő listán: a kijelölt sorok
eredeti anyagait állítja vissza és kiveszi őket a listából; a geometriát megtartja. Az objektum később újra hozzáadható.
A létrehozott shader-node-ok megmaradnak; a műveletek Undo-val visszavonhatók.

TÖBBES KIJELÖLÉS ÉS BEÁLLÍTÁSMÁSOLÁS — 2.0
Ctrl+kattintás: több sor. Shift+kattintás: összefüggő tartomány.
A paraméterpanel az aktív sor beállításait mutatja, csak azt szerkeszti.
Az azonos beállításokhoz:
1. Állíts be egy mintaobjektumot.
2. Jelöld ki a célokat a listában, majd Ctrl+kattintással utolsóként a mintát.
3. Copy active Distance / Dirt settings to selected.
A forrás az aktív sor (a paraméterpanel tetején látható név); a gomb
súgójában is ellenőrizhető. Legalább két kijelölt sor kell a másoláshoz.
A másolás a módot, Distance, Dirt, Strength, Falloff és Noise beállításokat
adja át; nem köti össze a vezérlőket, utána továbbra is függetlenek.
Displacement, Match, anyagok és viewport/preview kapcsolók nem másolódnak.
A Dirt ground-only korlátozás a cél saját ground-kapcsolatát használja.

Remove / restore: a kijelölt elemek eltűnnek a listából és visszakapják
az eredeti anyag-hozzárendelést, proxy esetén az eredeti material-slotokat.
A Delete csak akkor indítja ezt, ha a lista van fókuszban.
Az eredeti anyag a blend setup létrehozása előtti állapotot jelenti.
Az inaktív shader-node-ok megmaradnak, a geometriák nem törlődnek.
Mind a csoportos törlés/visszaállítás, mind a másolás egy Ctrl+Z-vel visszavonható.
A többes kijelölés, másolás, független displacement megőrzése, csoportos
visszaállítás és Undo GUI-val vezérelt Maya standalone tesztben ellenőrizve.

RÉGEBBI SETUP
A Setup menüben a régi 1.1/1.2-es setupok is szerepelnek. Kiválasztáskor
a tool objektumonként külön vezérlésre alakítja őket, megőrizve a tool
paramétereit, Dirt-módját, preview-állapotát és material-hozzárendeléseit.
A régi node-ok inaktív állapotban megmaradnak. A migráció Undo-val
visszavonható. Tetszőlegesen kézzel átépített shader-gráfok másolása nem cél.
A Distance alapértelmezés az új objektumokra vonatkozik; a meglévő Dirt
beállításokat nem írja felül.

ÚJ, ÁTMÉRETEZHETŐ FELÜLET
Klasszikus Maya-megjelenés: a Maya saját színei, gombjai és csúszkái.
Az 1.4-es elrendezés és görgetés megmaradt, egyedi színezés nélkül.
A paraméterek külön görgethetők; a geometrialista és az állapotsor helyben marad.
A hosszú objektumnevek fölött az egérrel megjelenik a teljes név.
A saját ikon be van építve: az ablakhoz nem kell külön képfájl.
Shelf-gombhoz a mellékelt object_blend_icon.png használható a Shelf Editorban.

KOMPAKT FELÜLET
Distance: csak a Distance mező és a közös vezérlők jelennek meg.
Dirt: csak a Dirt mezők és a közös vezérlők jelennek meg.
Distance + Dirt: mindkettő megjelenik; a két maszk SZORZATA adja az átmenetet.
A Noise és Dirt details alapból összecsukott. A sorok végén látszik az aktív mód.
Strength: anyagkeverés erőssége. Falloff: a végső maszk hatványkitevője.
Noise: zaj mennyisége, térbeli mérete, frekvenciaaránya.
Dirt radius / falloff: occlusion sugár és lecsengés.
Only ground can occlude: csak a talaj takarása számít; kikapcsolva a jelenet.
Ignore self occlusion: alapból bekapcsolva. Saját mélyedésekhez ezt és
a talajra korlátozást is ki kell kapcsolni.

OBJECT MATCH — ISMÉTELT HOZZÁADÁS HELYETT SZERKESZTÉS
Jelöld ki a geometriákat Mayában, majd Match to ground / Edit selected.
Egy közös panel nyílik a betöltött kijelöléshez. Objektumonként egy újra
használható vezérlés készül; az újranyitás nem duplikál anyagokat vagy
korrekciós láncot. Több objektumnál az első értékei látszanak, és csak a
megváltoztatott paraméter kerül mindegyikre. Más Maya-kijelöléshez nyomd meg
újra a gombot: a nyitott panel mindig a megnyitáskor betöltött objektumokat szerkeszti.

Exposure (stops): a base color világossága. -1 felezi, +1 duplázza.
Saturation shift: a base color telítettségének eltolása.
Roughness shift: a reflexiós roughness eltolása, 0..1 közé korlátozva.
Pozitív érték szétteríti a csillanást; glossiness módban is ugyanez az irány.
Reflection gain: a meglévő reflexióerősség szorzója; 1 az eredeti.
Advanced / Emission gain: önvilágítás szorzója; 1 az eredeti.
Reset match adjustments: csak az új match paramétereket nullázza/alaphelyzetbe teszi.
A meglévő textúrák és korábbi anyagbeállítások a kiindulási alap maradnak.
A létrehozás és a változtatások Undo-val visszavonhatók.

Ez kézi lookdev eszköz, nem automatikus talajszín-mintavétel. V-Ray IPR-ben
értékeld. Először a világosságot, majd a roughnesst állítsd; túl színes
objektumnál a telítettséget is. A Reflection gain kiegészítő művészi vezérlő.
A base color sötétítése nem helyettesíti a fények / csillanások kezelését.
A fémes és összetett, coat/SSS anyagok további anyagbeállítást igényelhetnek.

Blend setup nélkül is működik. A kijelölt objektum alapanyagát korrigálja;
a ráblendelt ground coatot és a talajt nem változtatja. Render-mask preview
alatt is a valódi alapanyaghoz kapcsolódik. Restore selected a blend
létrehozása előtti anyagot állítja vissza; az inaktív node-ok megmaradnak.
VRayMtl és VRayBlendMtl base ág támogatott; helyi proxy-slotok is.
A tool eddigi geometriakorlátai itt is érvényesek.

A shader/SG példányokat elkülöníti, a forrás-textúrákat megosztva hagyja.
Egy objektum több proxy-slotját ugyanaz a vezérlés állítja; slotonként
külön shaderhálózat szükséges. Az „egy korrekció” egy szerkeszthető setupot
jelent, nem egyetlen technikai node-ot: roughness/reflexió utility node-okat használ.
Ha a base coloron már volt V-Ray Color Correction, annak másolatát használja
újabb sorba kötött CC helyett. Korábbi verzióval kézzel felhalmozott láncokat
nem bont le automatikusan, így a meglévő look nem vész el.

VIEWPORT ÉS MASZK
Viewport radius guides: élő, a célobjektum pivotját követő sugárjelölések.
Kék = Distance, narancs = Dirt. A mód szerint eltűnik a nem használt jelölés.
A sugár változtatását követik, és a beállítás a jelenettel menthető.
Ezek távolsági REFERENCIAKARIKÁK, nem felület menti falloff-kontúrok és nem
valódi AO-maszkok. A pivot nem feltétlenül az érintkezési pont.
A tool korábbi verziójában nem volt külön viewport-falloff rajzolás.
Render mask preview: az adott objektum shader-maszkja V-Ray renderben / IPR-ben.
A standard Maya viewport nem helyettesíti a V-Ray raytracinget.

DISPLACEMENT — KÜLÖN KAPCSOLHATÓ
Válassz egy objektumsort. A DISPLACEMENT · DISTANCE MASK panel közvetlenül
a Blend mód alatt látszik, mindig nyitva. A Ground gain/shift mezők már
kikapcsolva is látszanak, de csak a Blend ground displacement bekapcsolásával
szerkeszthetők. Proxy célobjektumnál is aktív a panel (VRayDisplacementMtl támogatás szükséges).
Alapból kikapcsolva; objektumonként kapcsolható, a régi setupokon is.
Bekapcsolva: (1 - maszk) * objektum magasság + maszk * ground magasság,
majd ehhez adódik a Contact height távolsági eltolása.
Kikapcsolva pontosan a korábbi displacement-hálózat kimenete működik.
Ground gain: a talaj displacement-térképének szorzója.
Ground shift: a talaj magasságának eltolása a keverés előtt.
A maszk a Distance ág, annak zaj/falloff/strength beállításaival, 0..1 között.
Dirt módban is ez a külön Distance ág vezérli, nem az occlusion.
Az újrakapcsolás ugyanazt a hálózatot használja, nem épít újabb réteget.
A kapcsoló és értékek a jelenettel menthetők, Undo támogatott.

Jelenleg skalár displacement támogatott, mesh objektumok shading groupjából.
A ground shading groupján legyen displacement bekötés. Az objektumé hiányozhat,
ilyenkor annak alapmagassága 0. Vector displacement vagy külön VRayDisplacement-set esetén a bekapcsolás
hibával megáll és visszavonódik. Proxy célobjektumok támogatása alább.
A tool a térképek magasságértékét keveri; a ground objektum külön V-Ray
amount/shift/subdivision beállításait nem másolja. A célobjektum beállításai
érvényesülnek. Eltérő skálához használd a Ground gain/shift mezőket.
UV-s térkép a célobjektum UV-ját használja. Folytonos talajrészlethez közös
world-space/triplanar mapping kell. A tool nem hegeszti össze a geometriát.
A keverés numerikus végpontjai, átmenete, kontaktmagasság megőrzése,
ki/be kapcsolása, újrahasználata, Undo, mentés/újratöltés és Restore tesztelve.
A displacement renderelt végeredménye nincs külön ellenőrizve.

PROXY DISPLACEMENT — 1.9
A proxy displacementet VRayDisplacementMtl biztosítja, material-slotonként.
A lokális V-Ray 7.40.03-mal ellenőrizve; régebbi verziónál a node meglétét
futás közben ellenőrzi, és hiány esetén egyértelmű hibát ad.
Nem konvertál mesh-re, és a .vrmesh fájlt nem módosítja.
Bekapcsoláskor a blend shader köré displacement-material kerül.
Kikapcsoláskor a proxy slotja visszakapja az eredeti blend shadert.
A render-mask preview ki/be kapcsolása megőrzi a displacement állapotát.
Ground gain/shift és Contact height működik; proxyn a Contact height is
csak a Blend ground displacement bekapcsolásakor érvényesül.
A ground továbbra is mesh, shading-groupon bekötött skalár displacementtel.

A proxyba sütött domborzat a geometriája része: azt nem lehet visszafejteni
vagy a maszkkal eltüntetni. Az új magasságeltolás ezen felül értendő.
Ha a proxy material-gráfjában már van VRayDisplacementMtl, a tool hibával
megáll, hogy ne adja kétszer hozzá a displacementet. Ennek összevonása
még nincs implementálva. A régi bekötés ilyen hibánál megmarad.
Valódi kétmaterialos .vrmesh-en ellenőrizve: slotonkénti bekötés, magasság-
végpontok és átmenet, kapcsoló, gain/shift/contact, újrahasználat, preview,
Undo, mentés/újratöltés, Restore, más proxy változatlansága és aktív GUI.
Renderelt képen a végeredmény nincs külön ellenőrizve.

PROXY ÉS MATERIAL FELTÉTELEK
Objektumonként egy mesh vagy új típusú VRayProxy shape támogatott.
Normál mesh-en egy material kell; célproxy több bekötött V-Ray materialt
is használhat. A forrás/talaj materialja egyértelműen egyetlen material legyen.
A proxy szabálynevek, indexek és eredeti materialok megmaradnak.
A proxy fájlját a tool nem módosítja és nem konvertálja mesh-é.
Külső material assignment fájl vagy helyi shader nélküli proxy esetén
csatlakoztass helyi materialokat vagy adj teljes objektumra V-Ray materialt.
VRayScene, referenciák, Maya DAG instance-ok és normál mesh-ek face-enkénti
materialjai nem támogatottak. UV-s textúrák a fogadó objektum UV-ját használják;
folytonos talajtextúrához közös world-space / triplanar mapping szükséges.

TESZTÁLLAPOT
Maya 2026 / helyi V-Ray 7.40.03: Distance alapértelmezés; hozzáadás és
duplikációvédelem; független maszkok; valódi többmaterialos .vrmesh hozzáadása;
preview; átnevezés; mentés/újratöltés; eltávolítás és visszaadás; hibakori
batch-hozzáadás visszavonása; régi közös setup beállításainak megőrzése;
sugárjelölések méretének, pozíciójának és mód szerinti láthatóságának követése
ellenőrizve. Az új Qt GUI három ablakméretben és mindhárom módban
offscreen kirajzolással ellenőrizve. A mezők módosítása, függetlensége,
sorválasztás és viewport-kapcsoló Maya standalone alatt tesztelve.
Color Correction: textúra / konstans / külön RGB bemenet, megosztott anyag
elszigetelése, roughness / glossiness, emissive, blend preview, proxy-slot,
Undo és hibás batch teljes visszavonása Maya standalone alatt ellenőrizve.
Object Match: újranyitás duplikáció nélkül, megosztott anyagok elkülönítése,
roughness/glossiness és reflexió/emisszió vezérlés, legacy CC, blend-preview,
proxy, hibakori rollback és a panel szerkesztés/Reset működése ellenőrizve.
Az élő Maya-ablak és a renderelt végeredmény külön nem ellenőrzött.

FORRÁSOK
https://www.youtube.com/watch?v=wDSHf1Upnp8
https://docs-chaos.atlassian.net/wiki/spaces/VMAYA/pages/111740629
https://docs-chaos.atlassian.net/wiki/spaces/VMAYA/pages/111740149
https://docs-chaos.atlassian.net/wiki/spaces/VMAYA/pages/111740574/VRayBlendMtl

Object Match paraméterek:
https://docs-chaos.atlassian.net/wiki/spaces/VMAYA/pages/111740715/VRayColorCorrection
https://docs-chaos.atlassian.net/wiki/spaces/VMAYA/pages/111739261

Displacement források:
https://docs-chaos.atlassian.net/wiki/spaces/VMAYA/pages/111740342
https://docs-chaos.atlassian.net/wiki/spaces/VMAYA/pages/111740629

Proxy displacement:
https://docs-chaos.atlassian.net/wiki/spaces/VMAYA/pages/125780202

2.0.1 — DISPLACEMENT NÉLKÜLI ASSET
Az asset saját displacement-térképe nem feltétel. Hiányában az alapérték 0,
a Blend ground displacement bekapcsolva a ground magasságát futtatja rá
a Distance maszk szerint. Külön tesztelve displacement nélküli mesh-en
és kétmaterialos proxyn. Kikapcsolva a korábbi állapotot kapja vissza.
A groundnak továbbra is kell displacement-forrás; bump/normal térkép
nem alakul automatikusan displacementté. A renderelt eredmény nem tesztelt.

2.1 teszt: teljes/hiányzó/részleges mesh UV és proxy unknown; elkülönített
telepítési mappában fájlfrissítés, backup, ikon és friss kód indítása ellenőrizve.
Shelf létrehozás/frissítés/duplikációvédelem szimulált Maya UI API-val tesztelve;
a valódi viewport-drop és Maya újraindítás utáni shelf nem volt élőben tesztelve.

2.1.1 — PRISM TELEPÍTÉSI JAVÍTÁS
A userShelfDir és userBitmapsDir több útvonalat is tartalmazhat. A telepítő
a userPrefDir személyes Maya-profilmappából vezeti le a scripts, icons és
shelves helyét; nem próbál a Prism ProgramData könyvtárába telepíteni.
A megadott Prism útvonallista esetére elkülönített regressziós teszt sikeres.
A korábbi félbemaradt telepítés után az új telepítőt húzd be; a meglévő saját
shelf-gombot frissíti. Az új fájlnevet tartsd meg a Maya import-cache miatt.
