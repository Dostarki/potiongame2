export const CARD_INFO = {
  1: { image: "/assets/cards/l1.jpg", text: "Climbs down the mine and carries potion up in a glass backpack." },
  2: { image: "/assets/cards/l2.jpg", text: "Works a hand pump machine that draws potion out of the ground." },
  3: { image: "/assets/cards/l3.jpg", text: "A small drill rig and its operator tapping potion from below." },
  4: { image: "/assets/cards/l4.jpg", text: "A big drilling tower with its crew reaching the deep veins." },
  5: { image: "/assets/cards/l5.jpg", text: "Pulls potion from underground through a hose into a collector." },
  6: { image: "/assets/cards/l6.jpg", text: "A full potion factory with its own crew of workers." },
};

export const perMin = (n) => `+${Number(n).toLocaleString("en-US")}/min`;
