# QuickAlignment — Guide de l'utilisateur

Ligne ANTARES (SOLEIL) · retrouver les échantillons sur la plaquette, les garder sous le faisceau en tournant, et
choisir la rotation pour un point de la zone de Brillouin

## Sommaire

1. [Ce que fait QuickAlignment](#ce-que-fait-quickalignment)
2. [Démarrer le programme](#démarrer-le-programme)
3. [Coordonnées et moteurs](#coordonnées-et-moteurs)
4. [Onglet Samples : dessiner la plaquette](#onglet-samples--dessiner-la-plaquette)
5. [Onglet Stage & Optics : aller sur un échantillon](#onglet-stage--optics--aller-sur-un-échantillon)
6. [Onglet Rotate sample : tourner sans perdre l'échantillon](#onglet-rotate-sample--tourner-sans-perdre-léchantillon)
7. [Correct SN : remettre le point au foyer de l'analyseur](#correct-sn--remettre-le-point-au-foyer-de-lanalyseur)
8. [Trouver les angles pour un point de la zone de Brillouin](#trouver-les-angles-pour-un-point-de-la-zone-de-brillouin)
9. [Sessions, plaquette et configuration](#sessions-plaquette-et-configuration)
10. [Un temps de faisceau type](#un-temps-de-faisceau-type)
11. [Messages et que faire](#messages-et-que-faire)

---

## Ce que fait QuickAlignment

Sur ANTARES le faisceau est micrométrique ou plus petit, alors que la plaquette fait 18 × 15,5 mm. QuickAlignment
traduit la géométrie de la plaquette et des échantillons en **positions moteurs** :

- où se trouve chaque échantillon ou dispositif à l'orientation de départ (ST, SZ, SN à SRn = 120°, SRz = 0°) ;
- les ST / SN / SZ et la position de l'optique qui mettent un échantillon sous le faisceau, au foyer de l'analyseur ;
- après une rotation (SRn, SRz), les positions qui ramènent le même point sous le faisceau ;
- pour un cristal hexagonal 2D (graphène, WSe2, …), les SRn / SRz qui amènent Γ, K ou M au centre de la fente, et
  que faire quand la platine ne peut pas les atteindre.

Le programme ne déplace jamais de moteur : il calcule des nombres, que vous entrez dans le contrôle-commande de la ligne.

**L'exemple de ce guide.** Toutes les images suivent un cas réel : une **plaquette gating** portant le substrat
**RG_GMC** (Si, H = 0,525 mm) et son dispositif **R7G**, mesurés avec le **capillaire** en octobre 2026. Les
échantillons sont trouvés sur une photo de téléphone de la plaquette, R7G sur une photo au microscope ; R7G est amené
sous le faisceau à l'orientation de départ, sa position est corrigée une fois trouvé, puis la plaquette est tournée à
SRn = 92°, SRz = −24°, où R7G a été retrouvé sur la ligne à la position prédite.

## Démarrer le programme

Installation (une fois) : `pip install PyQt5 numpy matplotlib`. Puis double-cliquer sur **`QuickAlignment.py`**
(Windows : `QuickAlignment.pyw`, sans console), ou lancer `python QuickAlignment.py [session.json]`.

À chaque démarrage le programme demande quelle **plaquette** est montée et quelle **optique de focalisation** est
utilisée :

![Plaquette et optique au démarrage](images/guide/setup_dialog.png)

- **Standard Ta plate** : plaquette de 18 × 15,5 mm avec une rehausse de 11 mm de large, hauteur 5,0 mm.
- **Gating plate** : la même, avec un bloc de contact (3 plots en or, 4 vis) ; les échantillons vont seulement sur
  les 11 × 10,5 mm au-dessus du bloc.
- **Custom plate** : la plaquette de base avec votre propre bloc (longueur, largeur, centre y, hauteur depuis la face
  arrière).
- **Optique** : *zone plate + OSA* (95 eV uniquement) ou *capillary* (30–180 eV). La configuration la plus récente
  faite par le personnel de la ligne pour cette optique est chargée (affichée dans la barre d'outils).

## Coordonnées et moteurs

| nom | signification | plage |
|---|---|---|
| x, y | position sur la plaquette (mm), vue de face, languette en haut, origine = centre de la plaquette | – |
| H | hauteur de l'échantillon au-dessus de la surface de la plaquette (mm) | – |
| ST | le long du plan focal de l'analyseur ; ST < 0 déplace l'échantillon vers le haut à gauche (vue de dessus) | −6 … 6 mm |
| SN | perpendiculaire au plan focal de l'analyseur ; SN = 65 est la position de transfert | −30 … 65 mm ; sous SN_f la limite est une collision (voir *Anticollision*) |
| SZ | vertical | 35 … 45 mm |
| SRn | azimut autour de la normale ; SRn = 120° : plaquette verticale, languette en haut | utilisable 60 … 180° |
| SRz | rotation autour de la verticale ; SRz = 0 : plaquette parallèle au plan focal | utilisable −25 … +10° |
| PIX, PIY | platine piézo, 0 … 300 µm, centre 150 µm | – |

À l'orientation de départ, un point (x, y) de la plaquette est sous le faisceau à **ST = ST0 − x, SZ = SZ0 − y**, et
un échantillon de hauteur H est au foyer de l'analyseur à **SN = SN_f + H** (ST0, SZ0, SN_f viennent de la
configuration). Les champs moteurs refusent les valeurs hors course.

## Onglet Samples : dessiner la plaquette

![Onglet Samples](images/guide/samples_tab.png)

L'image montre la plaquette de l'exemple après *From photo…* (section suivante) : le substrat RG_GMC avec son
dispositif R7G (sélectionné, repère bleu), et une petite puce S2. La croix rouge est le centre de la plaquette
(x = y = 0) ; le cadre gris est la zone d'échantillons (plaquette gating : 11 × 10,5 mm au-dessus du bloc de contact).

- **Dessiner un échantillon** : glisser sur une partie vide de la plaquette. Le **déplacer** en le faisant glisser,
  le **redimensionner** par un bord ou un coin (positions arrondies à 0,1 mm). Ou *Add sample* puis taper les valeurs.
- **Tableau** : nom, x, y, longueur L, largeur W et hauteur H se tapent exactement (non arrondis). *Default H* est la
  hauteur des nouveaux échantillons (0,525 mm : un wafer Si standard). *Type* indique *sample*, ou *substrate (n)*
  avec le nombre de ses dispositifs.
- **Dispositifs sur un substrat** : sélectionner le substrat, *Add device*, choisir les deux bords de référence
  (*X ref* left/right, *Y ref* bottom/top) et les distances dx, dy au centre du dispositif, ou faire glisser le repère
  bleu. Le tableau et la ligne en dessous donnent aussi la position x, y du dispositif sur la plaquette. Les
  dispositifs suivent leur substrat ; un substrat avec dispositifs n'apparaît que par ses dispositifs dans les listes
  de cibles (par ex. *RG_GMC/R7G*).
- **Status** : `ok`, ou le problème (hors de la zone, chevauchement, dispositif hors du substrat). Les éléments rouges
  du dessin ont un problème.
- Molette = zoom, bouton du milieu = déplacer, clic droit = plaquette entière, Suppr = effacer la sélection (*Delete
  selected*). La ligne du bas donne les coordonnées plaquette sous la souris.

### Échantillons depuis une photo

Au lieu de les dessiner, les échantillons peuvent être trouvés sur une photo de la plaquette prise d'en haut (côté
échantillons ; une photo de téléphone suffit). Appuyer sur **From photo…** :

![Échantillons depuis une photo](images/guide/photo_dialog.png)

1. *Open photo…*. La vue de droite montre le modèle de la plaquette avec les quatre coins de la zone d'échantillons
   numérotés **1–4** ; celui à cliquer ensuite est en **rouge**. Cliquer ce point sur la photo, puis le rouge suivant
   (1 haut gauche, 2 haut droit côté languette, 3 bas droit, 4 bas gauche ; plaquette gating : 3 et 4 sont où la zone
   rencontre le bloc de contacts). Molette = zoom (zoomer autant que nécessaire pour placer le point), bouton du milieu
   = déplacer, clic droit = photo entière ; faire glisser les repères ensuite pour affiner. *Clear points* recommence.
2. La photo est projetée sur le modèle de la plaquette (vue de droite, contours bleus). Vérifier que les contours sont
   sur la plaquette. Le curseur donne les coordonnées plaquette (x, y en mm) dans la vue de droite et sur la photo.
3. Les échantillons sont trouvés par leur couleur (cadres verts, magenta = ce qui est retenu) :
   - *colour of picked samples* (par défaut) : cliquer sur un échantillon, sur la photo ou dans la vue de droite, pour
     prendre sa couleur (*Pick sample colour* pour une autre sorte d'échantillon) ; seules les régions proches de ces
     couleurs sont retenues, sans la laque d'argent ni la colle.
   - *colour different from the bare plate* : tout ce qui est sur la plaquette, laque d'argent et colle comprises. Si
     les échantillons couvrent presque toute la zone, *Pick bare plate colour* puis cliquer sur la plaquette nue.
   - *ΔE threshold* : l'écart de couleur (CIELAB) qui les sépare ; *min. size* écarte les poussières ; *border left
     out* ignore le bord de la zone ; *noise filter* comble les petits trous (reflets) et retire les points isolés.
   - Les pastilles après *sample colours* sont les couleurs prises ; *Clear* les oublie. *show what is taken* affiche
     ou cache le magenta ; *photo opacity* règle la transparence de la photo sur le modèle.
4. Corriger à la main. Tous les cadres de la liste sont ajoutés ; *sélectionner* des cadres en cliquant dessus dans la
   vue de droite (Ctrl + clic : plusieurs) ou sur leurs lignes, puis : **Delete selected** (ou Suppr) retire ce qui
   n'est pas un échantillon, **Merge selected** réunit les morceaux d'un échantillon coupé par de la laque ou des fils.
   **Draw box** puis glisser dans la vue de droite ajoute un échantillon non trouvé. Ces corrections restent quand le
   seuil change ; *Undo hand edits* les oublie. Dans l'exemple, la petite puce de gauche est coupée en cinq morceaux
   par sa laque d'argent : ils sont sélectionnés ensemble et réunis en S2 (ΔE « 9 (merged) »).
   Les **noms** se tapent dans le tableau (ici S1 → RG_GMC) ; la colonne *Devices* compte les dispositifs marqués dans
   l'onglet 2.
5. Entrer la **hauteur H** (invisible d'en haut ; par défaut *Default H*), par échantillon dans le tableau ou avec
   *Set H of all*.
6. Si besoin, placer les dispositifs sur une deuxième photo (onglet 2, ci-dessous), puis **Add to plate**. *Remove the
   samples already on the plate* remplace les échantillons présents.

Les cadres sont les rectangles englobants de ce qui a été trouvé, en coordonnées plaquette ; ils se déplacent, se
redimensionnent et reçoivent des dispositifs comme les échantillons dessinés. La précision dépend des clics sur les
coins (environ 0,1–0,3 mm) ; *Found here* dans l'onglet Stage & Optics corrige le reste. Tout est calculé sur
l'ordinateur, rien n'est envoyé.

**Bien placer les coins.** Ce sont les coins de la **partie surélevée** (dessus de la rehausse = zone d'échantillons),
pas ceux de la plaque de fond, plus large, en dessous. Un coin usé ou arrondi se place à l'intersection des deux bords
droits prolongés. Vérifier dans la vue de droite que le contour bleu suit les bords de la rehausse et la plaque de
fond tout autour : si un coin est faux, toute la plaquette est déformée.

#### Onglet 2 : dispositifs sur une deuxième photo

La photo de la plaquette montre où est un substrat, mais rarement ses dispositifs ; une photo plus proche (microscope,
appareil) montre les dispositifs mais souvent pas les bords du substrat. Les deux photos sont mises en correspondance
par des points que vous marquez sur les deux :

![Dispositifs sur une deuxième photo](images/guide/photo_devices.png)

1. Choisir le **substrat** (ou sélectionner son cadre dans l'onglet 1). La vue de gauche montre la photo de la
   plaquette autour de lui, déjà en coordonnées plaquette. **Open device photo…** (vue de droite).
2. *mark the same point on both* : cliquer à gauche un détail visible aussi sur la photo des dispositifs (point de
   laque, coin d'un motif, rayure), puis le même détail à droite ; repères numérotés, déplaçables. Avec 2 paires la
   photo est placée par rotation + échelle + translation, avec 3 par une application affine, avec 4 ou plus par une
   perspective. La ligne au-dessus des vues donne l'écart des points (µm) : avec plus de paires que nécessaire, il
   révèle un point faux. Le contour du substrat (orange) est tracé sur la photo des dispositifs pour vérifier.
3. *mark devices* : cliquer chaque dispositif sur la photo des dispositifs (ou à gauche). Le tableau donne sa position
   sur la plaquette, son substrat et dx, dy aux bords gauche / bas du substrat ; y renommer les dispositifs, effacer les
   faux. Les dispositifs n'ont pas de hauteur : ils sont à la surface de leur substrat.
4. Une autre photo de dispositifs (autre substrat, autre partie) peut être ouverte : les dispositifs déjà marqués
   gardent leur position. *Add to plate* ajoute chaque dispositif à l'échantillon sur lequel il se trouve (ceux hors de
   tout échantillon sont écartés).

Dans l'exemple, la photo des dispositifs est une image au microscope du centre de RG_GMC. Deux détails se voient sur
les deux photos : le point **1**, la goutte de laque d'argent au-dessus du centre (une tache noire au microscope), et
le point **2**, le trou rond du motif d'électrodes (le disque violet). R7G est ensuite cliqué sur le flocon du canal
entre les deux : x = 1,712, y = 3,090 mm. Avec deux paires seulement l'écart vaut toujours 0 µm ; une troisième paire,
quand un détail s'y prête, vérifie la correspondance.

La précision est celle de la photo de la plaquette (clics des coins, 0,1–0,3 mm) plus celle de la mise en
correspondance.

Une fois les échantillons dessinés, appuyer sur **Samples placed → Stage**.

## Onglet Stage & Optics : aller sur un échantillon

![Onglet Stage & Optics](images/guide/stage_tab.png)

Le cadre vert donne, pour chaque échantillon et dispositif, les **ST / SZ / SN à l'orientation de départ**
(SRn = 120°, SRz = 0°, PIX = PIY = 150 µm) qui mettent son centre sous le faisceau, au foyer de l'analyseur. Dans
l'exemple R7G est listé à ST = −2.662, SZ = 37.540, SN = 0.000 (*plate centre* est le centre de la plaque de fond,
pour repère).

1. Entrer les positions moteurs actuelles (valeurs absolues, comme dans le contrôle-commande). PIX, PIY sont la
   platine piézo : les calculs les prennent tels qu'entrés (les positions de départ ci-dessus sont pour le piézo
   centré).
2. Choisir une **Target** et appuyer sur **Bring target onto the beam** : ST et SZ sont calculés pour les SN, SRn,
   SRz, PIX, PIY entrés (**SN gardé**, comme d'habitude). Le texte indique la distance de la cible au foyer de
   l'analyseur le long du faisceau (en rouge au-delà de 50 µm : les spectres seraient déformés) et le ΔSN qui
   l'annulerait. Seulement si elle est jugée trop grande, **Correct SN** donne SN, ST, SZ qui mettent la cible au
   foyer de l'analyseur (voir [Correct SN](#correct-sn--remettre-le-point-au-foyer-de-lanalyseur)). Si un moteur sortait de sa course, ou si la plaquette touchait
   l'optique ou l'analyseur, rien n'est changé et la raison est donnée. Sur l'image, R7G est amené sous le faisceau à
   SRn = 120°, SRz = 0° : avec SN = 0 gardé, il est au foyer de l'analyseur.
3. **Optique** : *Type* est l'optique utilisée (zone plate + OSA, ou capillaire) ; entrer sa position et appuyer sur
   **Update schematic & optics**. Le schéma montre le faisceau, le foyer de l'analyseur, l'optique et la position
   **nécessaire** pour focaliser sur la surface éclairée (sur l'image le capillaire est à 60.04, il faut 59.6926).
   *Use required position* la copie dans le champ.
4. Après une focalisation à la main, **Set as optics reference** prend l'état actuel comme référence optique pour
   cette session.

**Le schéma** (redessiné seulement avec *Update schematic & optics*) :

- *Top view* (vue de dessus, faisceau vers le haut) : la plaquette et ses échantillons (orange) vus d'en haut, le
  faisceau (ligne rouge, × = tache du faisceau sur la surface), le nez de l'analyseur (bleu) avec son cône
  d'acceptance (orange clair) et son foyer (+ bleu), le plan focal de l'analyseur (tirets violets), l'optique avec
  son foyer (○) et sa position. Les pièces que la plaquette toucherait sont en rouge.
- *Sample plane, front view* : la plaquette vue le long du faisceau, tournée de SRn ; les axes donnent les ST, SZ qui
  amènent un point sous le faisceau à SRz = 0. × = tache du faisceau, + bleu = foyer de l'analyseur projeté sur la
  surface, ○ violet = axe SRn. La souris sur cette vue donne (sous les vues) ces ST, SZ, la position x, y sur la
  plaquette et l'échantillon qui s'y trouve.

### Found here : corriger le dessin

![Found here](images/guide/found_here.png)

La photo (ou le dessin) est juste à 0,1–0,3 mm près : un dispositif se trouve donc en général un peu à côté de sa
position listée. Une fois qu'il est vraiment **sous le faisceau et au foyer de l'analyseur**, entrer les positions,
choisir le dispositif sous *Found* et appuyer sur **Found here: correct its sample**. La fenêtre demande confirmation
et donne l'erreur du dessin (Δx, Δy sur la plaquette, ΔH en hauteur) ; *Yes* déplace l'échantillon avec tous ses
dispositifs, les autres restent. Toutes les prédictions utilisent ensuite la position corrigée (enregistrée avec la
session) ; la liste des positions de départ est mise à jour.

Dans l'exemple R7G est trouvé à ST = −2.4601, SZ = 37.8095, SN = 0 (SRn = 120°, SRz = 0°) : il était dessiné
0,20 mm trop à droite et 0,27 mm trop haut. Une correction de plus de 0,3 mm, ou le même décalage pour tous les
échantillons, suggère une configuration périmée : prévenir le personnel de la ligne. Utiliser *Found here* à
SRz = 0° quand c'est possible : là, SN gardé veut dire « au foyer de l'analyseur » ; après une rotation SRz avec SN
gardé, le point n'est en général pas au foyer de l'analyseur, et ΔH serait faux.

### Anticollision

Après *Update*, la ligne sous les moteurs donne la **plage sans collision** de ST, SN et SZ aux positions entrées (un
moteur déplacé, les autres et l'optique gardés) et ce qui fixe chaque limite, par ex. *SN −4.1 (OSA) … 65*. La vue de
dessus montre à l'échelle le nez de l'analyseur (MBS A1, à 30 mm du foyer), la zone plate et l'OSA (plaques minces ;
l'OSA ne bouge pas quand la zone plate refocalise) ou le capillaire, en rouge quand la plaquette les touche. *Bring
target onto the beam*, *Correct SN* et l'onglet Rotate refusent une position où la plaquette toucherait quelque
chose. Baisser SN rapproche la surface de l'optique et de l'analyseur : SN n'est limité que vers le bas. ST et SZ sont
libres pour une plaquette parallèle au plan focal, et limités quand SRz l'incline ou quand quelque chose dépasse (vis
de la plaquette gating). Les dimensions sont des estimations gardées dans la configuration : si on les connaît mieux, entrer les **distances de travail** (face avant de
l'OSA, de la zone plate ou du capillaire au foyer) dans les champs sous la position de l'optique (pour la session).
Garder une distance de sécurité et surveiller la caméra.

## Onglet Rotate sample : tourner sans perdre l'échantillon

![Onglet Rotate sample](images/guide/rotate_tab.png)

1. **Current position** : les positions avec le point d'intérêt sous le faisceau et au foyer, et la position de
   l'optique (*From Stage tab* les copie).
2. **Wanted angles** : les nouveaux SRn et SRz (ou *Find angles for a BZ point…*, sections suivantes).
3. **Compute new position** : ST et SZ avec le piézo centré et **SN gardé**, et la position de l'optique qui
   refocalise (le tableau donne *now*, *new* et l'écart Δ). Le point suivi est le point de la plaquette sous le
   faisceau à la position actuelle (ligne *Point:* : ce qui s'y trouve et ses x, y). Le texte indique la distance du
   point au foyer de l'analyseur, *downstream* (plus loin le long du faisceau) ou *upstream*, et sa distance actuelle
   selon le modèle (en rouge au-delà de 50 µm : les spectres seraient déformés). SRn seul garde le plan de la
   surface ; SRz non.
4. Seulement si le point est trop loin du foyer, cocher **Correct SN** (décoché à chaque nouveau calcul ; voir la
   section suivante) pour voir SN, ST, SZ et l'optique qui mettent le point **au foyer de l'analyseur**. Si une
   course moteur ne le permet pas, la position atteignable la plus proche est donnée avec sa distance au foyer.
5. **Send to Stage & Optics tab** reprend la solution affichée (cochée : la solution corrigée), refusé si hors course
   ou si la plaquette touchait quelque chose.

**Exemple.** R7G est sous le faisceau à SRn = 120°, SRz = 0° (ST = −2.4601, SZ = 37.8095, SN = 0, capillaire
59.6926) ; voulu : SRn = 92°, SRz = −24°. Avec SN gardé, ST = −6.0561, SZ = 38.9759 et le capillaire à 61.7277
remettent R7G sous le faisceau, mais à 2035 µm en aval du foyer de l'analyseur (rouge), et ST sort juste de sa course
par défaut (−6 … 6) : *Out of range … use the corrected solution*. Avec *Correct SN* : ST = −4.6171, SZ = 38.9759,
SN = −1.4390, capillaire inchangé : R7G au foyer de l'analyseur, tout dans les courses. *Send to Stage & Optics tab* :

![R7G retrouvé après la rotation](images/guide/rotate_found.png)

L'onglet Stage montre maintenant R7G **retrouvé** aux nouveaux angles : dans la vue du plan de l'échantillon la
plaquette est tournée à SRn = 92° (28° depuis l'orientation de départ) et la tache du faisceau (×) est sur R7G, au
foyer de l'analyseur (+) ; la vue de dessus montre la plaquette tournée de SRz = −24°. *Bring target onto the beam* /
*Correct SN* y donnent les mêmes positions.

**Vérifié sur la ligne** : à SRn = 92°, SRz = −24° avec SN gardé à 0, R7G a été trouvé à ST = −6.0479,
SZ = 38.9880, capillaire 61.74, à 8 µm, 12 µm et 0.01 de la prédiction avec SN gardé ci-dessus. La platine atteignait
alors ST = −6.05 : si votre course ST dépasse le −6 … 6 par défaut, l'entrer dans *Configuration… → Motor limits*.

## Correct SN : remettre le point au foyer de l'analyseur

![SN gardé et Correct SN après la même rotation](images/guide/correct_sn.png)

L'analyseur recueille les électrons d'un seul point fixe de l'espace, le **foyer de l'analyseur** (+ bleu ; le plan
focal de l'analyseur est la ligne « SN = 0 » de la caméra). Le point mesuré doit être sous le faisceau **et** en ce
point.

- **ST et SZ** déplacent la plaquette en travers du faisceau : ils amènent le point sur la ligne du faisceau. L'endroit
  où il se trouve alors le long du faisceau dépend de **SN**, qui déplace la plaquette selon sa normale (à 45° du
  faisceau).
- **SRn** tourne la plaquette autour de sa propre normale : la surface reste dans son plan, le point reste au foyer de
  l'analyseur dès que ST, SZ le suivent.
- **SRz** tourne la plaquette autour d'un axe vertical qui ne passe pas par la surface (dans la configuration
  actuelle, à environ 2,6 mm derrière le dessus de la rehausse). Avec ST, SZ qui suivent et **SN gardé**, le point
  reste sous le faisceau mais glisse **le long** de celui-ci, loin du foyer de l'analyseur. L'optique refocalise sur le
  point, la tache reste petite ; mais les électrons viennent d'un point hors du foyer de l'analyseur : les échelles
  d'énergie et d'angle sont déformées et l'intensité baisse. Au-delà de 50 µm le programme l'écrit en rouge.
- **Correct SN** déplace SN, avec ST qui compense (SN n'est pas le long du faisceau), pour remettre le point **au**
  foyer de l'analyseur. L'optique revient alors là où elle focalise sur le foyer de l'analyseur.

Dans l'exemple (à gauche : SN gardé, à droite : Correct SN, tous deux à SRn = 92°, SRz = −24°), la tache sur R7G est à
2,0 mm en aval du foyer de l'analyseur avec SN gardé ; SN = −1.439 avec ST = −4.617 l'y remet, le capillaire à 59.6926
comme avant la rotation.

SN est gardé par défaut parce que la platine se conduit ainsi (la surface reste sur la ligne de la caméra, l'optique
refocalise) et parce que *Correct SN* est absolu : il repose sur le SN_f et les axes de rotation de la configuration.
L'utiliser quand la distance est en rouge, et regarder la ligne d'anticollision : un SN plus bas rapproche la surface
de l'optique et de l'analyseur. Dans l'onglet Stage, *Correct SN* est un bouton (pour la cible choisie aux angles
entrés) ; dans l'onglet Rotate, une case à cocher.

## Trouver les angles pour un point de la zone de Brillouin

Sous *Wanted angles*, **Find angles for a BZ point…** répond, pour les cristaux hexagonaux 2D, à la question
*« de combien tourner SRn et SRz pour que K soit au centre de la fente, la fente selon Γ–K et le déflecteur proche de 0 ? »*

![Point de zone atteignable](images/guide/bz_reachable.png)

**À entrer** (lu sur le contour d'une carte dans ARPES viewer ; θ = angle du déflecteur, x du contour ; φ = angle le
long de la fente, y du contour) :

1. **The map** : SRn et SRz de la mesure (*From current position* les prend dans l'onglet Rotate), son énergie de
   photon, les angles de **Γ** et d'**un point K ou M**.
2. **Crystal** : la constante de réseau dans le plan a (préréglages : graphène 2,46 Å, WSe2 3,282 Å, WS2, MoSe2,
   MoS2, hBN).
3. **Wanted** : le point (Γ, K ou K′, K seul, K′ seul, M), la **direction de la fente** (Γ–K, K–M, Γ–M, M–K),
   l'énergie de photon de la nouvelle mesure, E − E_F du point (p. ex. −1,0 pour le haut de bande de valence de WSe2
   en K) et le travail de sortie (4,5 eV).

Appuyer sur **Compute**. Sous les entrées, *Γ–K on the map* compare la distance mesurée à la constante de réseau (un
écart de plus de 10 % signale un nombre, un point ou une énergie faux) et donne l'inclinaison de l'échantillon sur la
plaquette (prise en compte dans le résultat).

**Résultat** : *Reachable* quand, déflecteur à 0, le point est à |θ| ≤ 5° et |φ| ≤ 5° du centre de la fente, la
fente à moins de 2° de la ligne voulue, avec SRn 60 … 180° et SRz −25 … +10°. Le tableau donne tous les points
équivalents et les deux sens de rotation ; la première ligne est la recommandée (d'abord SRz ≤ 0 : faisceau plus
proche de la normale, spot plus petit ; puis la plus petite rotation). *Beam to normal* est l'angle d'incidence,
45° + SRz.

**Aperçu** : à gauche, la carte que vous mesurerez aux angles proposés (déflecteur en abscisse, angle de fente en
ordonnée ; le déflecteur a des lacunes au-delà de ±8° et s'arrête à ±12° ; le cadre vert est le ±5° accepté). À
droite, la zone 2D en impulsion, orientée comme votre carte actuelle, avec la carte actuelle (tirets) et la nouvelle
fenêtre de l'analyseur et la fente (orange).

**Use these angles** écrit SRn / SRz dans *Wanted angles* et calcule la nouvelle position. Mettre le déflecteur à 0
(et l'énergie de photon, si elle a changé).

### Quand ce n'est pas atteignable

Le manipulateur n'a **pas d'axe de tilt**. Conséquence : avec un point au centre de la fente et le déflecteur à 0, la
fente est toujours selon la ligne de Γ à ce point (Γ–K pour K). Une fente *perpendiculaire* (K–M, M–K) demande le
déflecteur à l'angle d'émission du point (15–20° à 95 eV), ce que l'analyseur fait mal :

![Coupe en bord de zone](images/guide/bz_zone_edge.png)

La fenêtre propose alors l'**alternative radiale** : K au centre, fente selon Γ–K ; la direction du déflecteur est
alors selon K–M, et une courte **carte en déflecteur** (|θ| ≤ 5°) donne la coupe K–M passant par K avec peu de
distorsion. *Show the radial alternative* y passe directement.

Quand l'angle d'émission est trop grand pour la plage de SRz, la fenêtre donne les **énergies de photon** auxquelles
le point est atteignable :

![Énergie de photon plus élevée nécessaire](images/guide/bz_photon_energy.png)

- ANTARES : 30–180 eV avec le **capillaire** ; la **zone plate ne fonctionne qu'à 95 eV**. Changer d'énergie avec la
  zone plate signifie passer au capillaire (réalignement, configuration capillaire).
- Si SRn est la limite, la fenêtre indique de combien **tourner l'échantillon sur la plaquette** au remontage.
- Si rien ne marche, il faut remonter l'échantillon ou choisir un autre point équivalent.

| exemple (E_F, travail de sortie 4,5 eV) | angle d'émission de K à 30 / 95 / 180 eV | K, fente selon Γ–K |
|---|---|---|
| WSe2, a = 3,282 Å, Γ–K = 1,28 Å⁻¹ | 29,6° / 15,2° / 10,8° | atteignable à 95 eV avec SRz ≈ −15° |
| graphène, a = 2,46 Å, Γ–K = 1,70 Å⁻¹ | 41,2° / 20,4° / 14,5° | 95 eV : SRz ≈ −20° ; 30 eV : non (il faut ≳ 61 eV) |

Les signes entre la platine et le contour d'ARPES viewer ont été vérifiés une fois (signe du déflecteur, 2026-09) ;
lors d'un nouveau type de mesure, vérifier que le point apparaît là où l'aperçu le montre.

## Sessions, plaquette et configuration

- **New / Open… / Save** (barre d'outils) : une session contient la plaquette, les échantillons et dispositifs (avec
  leurs corrections) et les positions moteurs, dans un fichier JSON. Le premier *Save* demande le nom du fichier.
  L'écriture est sûre : si elle échoue (disque plein, droits), l'ancien fichier reste intact et un message en donne
  la raison.
- **Change plate…** : une autre plaquette ; les échantillons sont gardés et ceux mal placés sont signalés.
- **Configuration…** : vue en lecture seule de la configuration utilisée (constantes de la platine et référence
  optique), faite par le personnel de la ligne. Une configuration plus ancienne peut être choisie pour la session.
  Sous *Motor limits*, les limites min / max de ST, SZ, SN, SRn et SRz peuvent être modifiées à la main (*Defaults*
  remet celles par défaut) ; *Apply limits* les utilise pour les champs de saisie, les contrôles de course et
  anticollision, et les enregistre dans `configs/motor_limits.json` pour les démarrages suivants.

![Fenêtre de configuration](images/guide/configuration_dialog.png)

## Un temps de faisceau type

1. Lancer QuickAlignment, confirmer plaquette et optique.
2. Trouver les échantillons sur la photo de montage (*From photo…*), placer les dispositifs sur une photo au
   microscope (onglet 2), ou les dessiner ; ou ouvrir la session préparée avant. *Samples placed → Stage*.
3. Aller au premier échantillon ou dispositif avec les ST / SZ / SN listés (SRn = 120°, SRz = 0°) ; le trouver avec le
   faisceau (caméra, carte de photoémission).
4. *Found here* : corriger sa position. Les autres tombent alors juste aussi.
5. Mesurer une carte à SRn = 120°, SRz = 0° ; lire Γ et un point K / M dans ARPES viewer.
6. *Find angles for a BZ point…* → *Use these angles* → *Compute new position* (cocher *Correct SN* si le point est à
   plus de 50 µm du foyer) → *Send to Stage & Optics tab*.
7. Enregistrer la session.

## Messages et que faire

| message | signification / que faire |
|---|---|
| *Out of range: ST = … (range …)* | le point n'est pas atteignable à ces angles ; choisir d'autres angles ou la solution corrigée ; si la platine va réellement plus loin, régler les limites dans *Configuration… → Motor limits* |
| *Collision: the plate would touch …* | à cette position la plaquette (ou un échantillon, une vis) heurterait l'optique ou l'analyseur ; rien n'est changé : choisir une autre position, ou reculer l'optique |
| *… in the analyzer acceptance cone: it would shadow the electrons* | l'optique est sur le trajet des électrons vers l'analyseur ; la retirer |
| *… µm from the analyzer focus* (rouge) | après une rotation SRz le point a quitté le plan focal : cocher *Correct SN* |
| *Correct the sample position?* | *Found here* : vérifier les positions et le dispositif, *Yes* déplace l'échantillon |
| *Found here* déplace un échantillon de plus de 0,3 mm | dessin faux, ou configuration périmée (moteurs réinitialisés) : demander au personnel |
| *The beam misses the plate* | ST / SZ ne mettent pas le faisceau sur la plaquette |
| *Check the input: Γ–K on the map is …* | constante de réseau, point ou énergie ne correspondent pas à la carte |
| *An unexpected error occurred* | le programme continue ; vérifier le dernier résultat, enregistrer la session et envoyer les détails au personnel |
